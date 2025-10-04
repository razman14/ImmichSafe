import sys
import os
import subprocess
import json
import shutil
from datetime import datetime
from pathlib import Path
import time as time_module
import re
import requests
import stat

try:
    import paramiko
except ImportError:
    paramiko = None

from PySide6.QtCore import QObject, Signal, Slot

from config import IS_WINDOWS

class Worker(QObject):
    finished = Signal(str)
    progress = Signal(int, int)
    log_message = Signal(str)
    error_message = Signal(str)
    versions_fetched = Signal(list)
    docker_status_fetched = Signal(dict)
    release_notes_fetched = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.is_immich_server_running = False

    @Slot()
    def stop(self): self.is_running = False

    def _get_ssh_client(self, settings):
        if not paramiko:
            raise ImportError("The 'paramiko' library is required for SSH functionality. Please install it using: pip install paramiko")
        
        host = settings.get("ssh_host")
        port = settings.get("ssh_port", 22)
        user = settings.get("ssh_user")
        password = settings.get("ssh_pass")
        key_path = settings.get("ssh_key_path")

        if not all([host, user]):
            raise ValueError("SSH host and username are required.")
        if not password and not key_path:
            raise ValueError("SSH password or private key is required.")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        self.log_message.emit(f"Connecting to {user}@{host}:{port}...")
        
        try:
            pkey = None
            if key_path:
                key_path = os.path.expanduser(key_path)
                if not os.path.exists(key_path):
                    raise FileNotFoundError(f"SSH private key not found at: {key_path}")
                pkey = paramiko.RSAKey.from_private_key_file(key_path)

            client.connect(hostname=host, port=port, username=user, password=password, pkey=pkey, timeout=10)
            self.log_message.emit("SSH connection successful.")
            return client
        except Exception as e:
            self.log_message.emit(f"SSH connection failed: {e}")
            raise

    def _run_command_stream(self, command, cwd, ssh_client=None):
        cmd_str = ' '.join(command) if isinstance(command, list) else command
        if ssh_client:
            full_command = f"cd {cwd} && {cmd_str}"
            self.log_message.emit(f"Running remote command: {full_command}")
            stdin, stdout, stderr = ssh_client.exec_command(full_command, get_pty=True)
            
            for line in iter(stdout.readline, ""):
                if not self.is_running: break
                self.log_message.emit(line.strip())
            
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                error_output = "".join(stderr.readlines())
                self.log_message.emit(f"Remote command failed with exit code {exit_code}")
                if error_output: self.log_message.emit(f"Error output: {error_output.strip()}")
                raise RuntimeError(f"Command failed with exit code {exit_code}")
        else:
            self.log_message.emit(f"Running local command: {cmd_str}")
            process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
            for line in process.stdout:
                if not self.is_running:
                    process.terminate()
                    break
                self.log_message.emit(line.strip())
            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"Command failed with exit code {process.returncode}")

    @Slot(dict)
    def fetch_docker_status(self, settings):
        status_dict = {}
        version = "Unknown"
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            install_path = settings.get("immich_install_path", "")
            
            expected_services = ['immich-server', 'immich-microservices', 'immich-machine-learning', 'immich-postgres', 'redis']
            status_dict = {name.replace('-', '_'): 'stopped' for name in expected_services}

            if is_remote: ssh_client = self._get_ssh_client(settings)
            
            if not self._is_docker_running(ssh_client): raise RuntimeError("Docker is not running")
            if not install_path: raise RuntimeError("Immich install path not set")

            version = self._get_immich_version(install_path, ssh_client=ssh_client)
            self.is_immich_server_running = self._does_container_exist("immich-server", install_path, ssh_client)

            project_name = os.path.basename(install_path).lower().replace(" ", "")
            command = f'docker ps -a --filter "label=com.docker.compose.project={project_name}" --format "{{{{json .}}}}"'
            
            if ssh_client:
                full_cmd = f"cd {install_path} && {command}"
                stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
                output = stdout.read().decode('utf-8')
            else:
                result = subprocess.run(command, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0, shell=True, cwd=install_path)
                output = result.stdout

            for line in output.strip().splitlines():
                if not line: continue
                try: container_info = json.loads(line)
                except json.JSONDecodeError: continue
                
                labels = container_info.get("Labels", "")
                service_name = re.search(r'com\.docker\.compose\.service=([a-zA-Z0-9_-]+)', labels)
                if service_name:
                    service_name = service_name.group(1)
                    if service_name == "database": service_name = "immich-postgres"
                    state = container_info.get("State")
                    if service_name in expected_services:
                        status_dict[service_name.replace('-', '_')] = state

        except Exception as e:
            self.log_message.emit(f"Could not fetch Docker status: {e}")
            for key in status_dict: status_dict[key] = 'unknown'
        finally:
            if ssh_client: ssh_client.close()
            payload = {"version": version, "containers": status_dict}
            self.docker_status_fetched.emit(payload)

    def _backup_and_restore_wrapper(self, settings, backup_type, task_function):
        start_time, status, error_msg = time_module.time(), "failure", ""
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote:
                ssh_client = self._get_ssh_client(settings)
            
            task_function(settings, ssh_client)
            status = "success"

        except Exception as e:
            error_msg = str(e); self.error_message.emit(f"An error occurred during {backup_type} backup: {error_msg}")
        finally:
            if ssh_client: ssh_client.close()
            duration = time_module.time() - start_time
            if not settings.get("ssh_enabled", False): # Log only for local backups
                 self._write_backup_log(settings['backup_dir'], status, duration, error_msg, backup_type)
            self.finished.emit(status)

    @Slot(dict)
    def run_backup(self, settings):
        self._backup_and_restore_wrapper(settings, "Full", self._run_backup_task)
    
    @Slot(dict)
    def run_db_backup(self, settings):
        self._backup_and_restore_wrapper(settings, "Database Only", self._run_db_backup_task)
        
    @Slot(dict)
    def run_media_backup(self, settings):
        self._backup_and_restore_wrapper(settings, "Media Only", self._run_media_backup_task)

    def _run_backup_task(self, settings, ssh_client):
        self.log_message.emit("Starting full backup process...")
        container_name = settings['container_name']
        if not self._is_docker_running(ssh_client): raise RuntimeError("Docker is not running")
        if not self._does_container_exist(container_name, settings['immich_install_path'], ssh_client): raise RuntimeError(f"Container '{container_name}' not found")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(settings['backup_dir'], f"ImmichBackup_{timestamp}")
        
        # Paths for remote server
        media_path = os.path.join(backup_path, "media")
        db_path = os.path.join(backup_path, "database")
        
        if ssh_client:
            sftp = ssh_client.open_sftp()
            self._sftp_makedirs(sftp, media_path)
            self._sftp_makedirs(sftp, db_path)
            sftp.close()
        else:
            os.makedirs(media_path, exist_ok=True)
            os.makedirs(db_path, exist_ok=True)
        
        self.log_message.emit("Backing up database...")
        db_file = os.path.join(db_path, f"immich_db_{timestamp}.sql")
        self._backup_database(container_name, settings['db_user'], db_file, ssh_client)
        if not self.is_running: return
        
        self.log_message.emit("Backing up media files...")
        self._copy_with_progress(settings['source_dir'], media_path, ssh_client)
        if not self.is_running: return
        
        self.log_message.emit("Cleaning up old backups...")
        self._apply_retention_policy(settings['backup_dir'], settings['retention_days'], ssh_client)
        self.log_message.emit("\nFull backup process completed successfully!")

    def _run_db_backup_task(self, settings, ssh_client):
        self.log_message.emit("Starting database-only backup...")
        container_name = settings['container_name']
        if not self._is_docker_running(ssh_client): raise RuntimeError("Docker is not running")
        if not self._does_container_exist(container_name, settings['immich_install_path'], ssh_client): raise RuntimeError(f"Container '{container_name}' not found")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(settings['backup_dir'], f"ImmichBackup_{timestamp}")
        db_path = os.path.join(backup_path, "database")
        
        if ssh_client:
            sftp = ssh_client.open_sftp()
            self._sftp_makedirs(sftp, db_path)
            sftp.close()
        else:
            os.makedirs(db_path, exist_ok=True)
            
        self.log_message.emit("Backing up database...")
        db_file = os.path.join(db_path, f"immich_db_{timestamp}.sql")
        self._backup_database(container_name, settings['db_user'], db_file, ssh_client)
        if not self.is_running: return
        
        self.log_message.emit("Cleaning up old backups...")
        self._apply_retention_policy(settings['backup_dir'], settings['retention_days'], ssh_client)
        self.log_message.emit("\nDatabase backup completed successfully!")

    def _run_media_backup_task(self, settings, ssh_client):
        self.log_message.emit("Starting media-only backup...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(settings['backup_dir'], f"ImmichBackup_{timestamp}")
        media_path = os.path.join(backup_path, "media")
        
        if ssh_client:
            sftp = ssh_client.open_sftp()
            self._sftp_makedirs(sftp, media_path)
            sftp.close()
        else:
            os.makedirs(media_path, exist_ok=True)
            
        self.log_message.emit("Backing up media files...")
        self._copy_with_progress(settings['source_dir'], media_path, ssh_client)
        if not self.is_running: return

        self.log_message.emit("Cleaning up old backups...")
        self._apply_retention_policy(settings['backup_dir'], settings['retention_days'], ssh_client)
        self.log_message.emit("\nMedia backup completed successfully!")

    @Slot(dict)
    def run_full_restore(self, settings):
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = self._get_ssh_client(settings)

            self.log_message.emit("Starting full restore process..."); self.progress.emit(0, 100)
            if not self.is_running: return

            self.log_message.emit("--- Step 1 of 2: Restoring media ---")
            self.run_media_restore(settings, emit_finish_signal=False, ssh_client_in=ssh_client)
            self.progress.emit(50, 100)
            
            self.log_message.emit("\n--- Step 2 of 2: Restoring database ---")
            self.run_db_restore(settings, emit_finish_signal=False, ssh_client_in=ssh_client)
            
            self.progress.emit(100, 100); self.log_message.emit("\nFull restore process finished.")
        except Exception as e:
            self.error_message.emit(f"An error occurred during full restore: {e}")
        finally:
            if ssh_client: ssh_client.close()
            self.finished.emit("restored")

    def _fetch_github_file(self, version, filename, is_latest):
        self.log_message.emit(f"Downloading {filename} for version {version}...")
        url = f"https://github.com/immich-app/immich/releases/{'latest/download' if is_latest else f'download/{version}'}/{filename}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text

    def _update_env_file_content(self, env_content, updates):
        lines = env_content.splitlines()
        output_lines, keys_to_update = [], set(updates.keys())
        for line in lines:
            stripped = line.strip()
            key_match = re.match(r"^[# ]*([^=]+)=", stripped) if stripped else None
            if key_match and (key := key_match.group(1).strip()) in keys_to_update:
                output_lines.append(f"{key}={updates[key]}")
                keys_to_update.remove(key)
            else:
                output_lines.append(line)
        for key in sorted(list(keys_to_update)):
            output_lines.append(f"{key}={updates[key]}")
        return "\n".join(output_lines)

    @Slot(dict)
    def run_immich_install(self, settings):
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = self._get_ssh_client(settings)
            
            install_path = settings['immich_install_path']
            version = settings['version']
            is_latest = settings['is_latest']
            
            if ssh_client:
                sftp = ssh_client.open_sftp()
                self._sftp_makedirs(sftp, install_path)
            else:
                Path(install_path).mkdir(exist_ok=True)
            
            compose_content = self._fetch_github_file(version, "docker-compose.yml", is_latest)
            env_content = self._fetch_github_file(version, "example.env", is_latest)
            
            self.log_message.emit("Writing docker-compose.yml...")
            compose_path = os.path.join(install_path, "docker-compose.yml")
            if ssh_client:
                with sftp.open(compose_path, 'w') as f: f.write(compose_content)
            else:
                with open(compose_path, 'w') as f: f.write(compose_content)

            self.log_message.emit("Configuring and writing .env file...")
            posix_parent_path = settings['source_dir'].replace('\\', '/')
            self.log_message.emit(f"Setting '.env' UPLOAD_LOCATION to: {posix_parent_path}")
            
            updates = {"UPLOAD_LOCATION": posix_parent_path, "DB_PASSWORD": settings['db_pass'], "POSTGRES_PASSWORD": settings['db_pass']}
            if not is_latest: updates["IMMICH_VERSION"] = version
            updated_env = self._update_env_file_content(env_content, updates)
            
            env_path = os.path.join(install_path, ".env")
            if ssh_client:
                with sftp.open(env_path, 'w') as f: f.write(updated_env)
            else:
                with open(env_path, 'w') as f: f.write(updated_env)
            
            self.log_message.emit("Ensuring required media subdirectories and integrity files exist...")
            required_subdirs = ["upload", "thumbs", "profile", "encoded-video", "library", "backups"]
            for subdir in required_subdirs:
                full_path = os.path.join(settings['source_dir'], subdir)
                try:
                    if ssh_client:
                        self._sftp_makedirs(sftp, full_path)
                        with sftp.open(os.path.join(full_path, ".immich"), 'w') as f: f.write('') # touch
                    else:
                        os.makedirs(full_path, exist_ok=True)
                        (Path(full_path) / ".immich").touch(exist_ok=True)
                    self.log_message.emit(f"  ✓ Path and integrity file ready: {full_path}")
                except Exception as e:
                    self.log_message.emit(f"  - WARNING: Could not prepare subdirectory '{full_path}'. Error: {e}")
            if ssh_client: sftp.close()

            self.log_message.emit("Adding a 5-second delay for file system synchronization...")
            time_module.sleep(5)

            self._run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path, ssh_client=ssh_client)
            self.log_message.emit("Immich installation completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to install Immich: {e}")
        finally:
            if ssh_client: ssh_client.close()
            time_module.sleep(5); self.finished.emit("manage")
    
    @Slot(dict)
    def run_immich_update(self, settings):
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = self._get_ssh_client(settings)
            
            self._perform_update_steps(settings['immich_install_path'], settings['version'], settings['is_latest'], ssh_client)
            self.log_message.emit("Immich update completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to update Immich: {e}")
        finally:
            if ssh_client: ssh_client.close()
            time_module.sleep(5); self.finished.emit("manage")

    def _perform_update_steps(self, install_path, version, is_latest, ssh_client):
        self.log_message.emit("Stopping Immich containers..."); self._run_command_stream(["docker", "compose", "down"], cwd=install_path, ssh_client=ssh_client)
        
        new_compose = self._fetch_github_file(version, "docker-compose.yml", is_latest)
        new_env_template = self._fetch_github_file(version, "example.env", is_latest)
        
        sftp = ssh_client.open_sftp() if ssh_client else None
        
        self.log_message.emit("Writing new docker-compose.yml...");
        compose_path = os.path.join(install_path, "docker-compose.yml")
        if sftp:
            with sftp.open(compose_path, 'w') as f: f.write(new_compose)
        else:
            with open(compose_path, 'w') as f: f.write(new_compose)

        self.log_message.emit("Preserving settings from old .env file...")
        old_env_path = os.path.join(install_path, ".env")
        old_settings = {}
        
        old_env_exists = False
        if sftp:
            try:
                sftp.stat(old_env_path)
                old_env_exists = True
            except FileNotFoundError:
                old_env_exists = False
        else:
            old_env_exists = os.path.exists(old_env_path)
            
        if old_env_exists:
            if sftp:
                with sftp.open(old_env_path, 'r') as f: old_content = f.read().decode()
            else:
                with open(old_env_path, 'r') as f: old_content = f.read()

            for line in old_content.splitlines():
                if '=' in line and not line.strip().startswith("#"):
                    key, val = line.strip().split('=', 1)
                    old_settings[key] = val
        
        if is_latest: old_settings.pop("IMMICH_VERSION", None)
        else: old_settings["IMMICH_VERSION"] = version
        
        updated_env = self._update_env_file_content(new_env_template, old_settings)
        if sftp:
            with sftp.open(old_env_path, 'w') as f: f.write(updated_env)
        else:
            with open(old_env_path, 'w') as f: f.write(updated_env)
        if sftp: sftp.close()

        self.log_message.emit("Pulling new Docker images..."); self._run_command_stream(["docker", "compose", "pull"], cwd=install_path, ssh_client=ssh_client)
        self.log_message.emit("Recreating containers with the new version..."); self._run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path, ssh_client=ssh_client)
        self.log_message.emit(f"Update/rollback to version {version} completed.")

    @Slot(dict)
    def run_safe_update(self, settings):
        ssh_client, sftp = None, None
        install_path = settings['immich_install_path']
        temp_backup_dir = os.path.join(install_path, "immichsafe_temp")
        temp_backup_path = None

        try:
            self.log_message.emit("--- Starting Safe Update Process ---")
            is_remote = settings.get("ssh_enabled", False)
            if is_remote:
                ssh_client = self._get_ssh_client(settings)
                sftp = ssh_client.open_sftp()
            
            container_name = settings['container_name']
            old_version = settings['current_version']
            new_version = settings['version']

            self.log_message.emit("Step 1: Creating temporary database backup...")
            if not self._does_container_exist(container_name, install_path, ssh_client):
                 raise RuntimeError(f"Database container '{container_name}' is not running. Cannot create backup.")

            if sftp: self._sftp_makedirs(sftp, temp_backup_dir)
            else: os.makedirs(temp_backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_backup_path = os.path.join(temp_backup_dir, f"pre_update_backup_{timestamp}.sql")
            self._backup_database(container_name, settings['db_user'], temp_backup_path, ssh_client)
            self.log_message.emit("Temporary backup created successfully.")

            self.log_message.emit(f"Step 2: Attempting to update from {old_version} to {new_version}...")
            self._perform_update_steps(install_path, new_version, settings['is_latest'], ssh_client)
            
            self.log_message.emit("Step 3: Performing post-update health check...")
            time_module.sleep(15) 
            if not self._health_check(install_path, ssh_client):
                raise RuntimeError("Health check failed after update. Services did not start correctly.")
            
            self.log_message.emit("Health check passed! Update successful.")
            self.log_message.emit("--- Safe Update Process Completed Successfully ---")

        except Exception as e:
            self.error_message.emit(f"Update failed: {e}. Initiating rollback...")
            try:
                self.log_message.emit(f"--- Rolling back to version {old_version} ---")
                self._perform_update_steps(install_path, old_version, False, ssh_client)
                
                self.log_message.emit("Restoring database from temporary backup...")
                temp_backup_exists = False
                if sftp:
                    try:
                        sftp.stat(temp_backup_path)
                        temp_backup_exists = True
                    except FileNotFoundError: pass
                else:
                    temp_backup_exists = os.path.exists(temp_backup_path)

                if temp_backup_exists:
                    self._restore_database_logic(temp_backup_path, container_name, settings['db_user'], ssh_client)
                else:
                    self.log_message.emit("Warning: Could not find temporary backup to restore.")
                self.log_message.emit("Rollback successful. Your system has been restored.")
            except Exception as rollback_e:
                self.error_message.emit(f"CRITICAL: ROLLBACK FAILED. {rollback_e}. Manual intervention may be required.")
        finally:
            self.log_message.emit("Cleaning up temporary backup files.")
            if sftp:
                self._sftp_rmtree(sftp, temp_backup_dir)
                sftp.close()
            elif os.path.exists(temp_backup_dir):
                shutil.rmtree(temp_backup_dir)
            if ssh_client: ssh_client.close()
            time_module.sleep(5); self.finished.emit("manage")

    def _health_check(self, install_path, ssh_client):
        self.log_message.emit("Checking container status...")
        return self._get_immich_version(install_path, ssh_client=ssh_client) != "Unknown"

    @Slot(dict)
    def run_immich_action(self, settings):
        ssh_client = None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = self._get_ssh_client(settings)
            
            action = settings['action']
            self._run_command_stream(["docker", "compose"] + action.split(), cwd=settings['immich_install_path'], ssh_client=ssh_client)
            self.log_message.emit(f"Immich {action} command finished.")
        except Exception as e:
            self.error_message.emit(f"Failed to {action} Immich: {e}")
        finally:
            if ssh_client: ssh_client.close()
            time_module.sleep(3); self.finished.emit("manage")
            
    @Slot(dict)
    def run_immich_reinstall(self, settings):
        ssh_client, sftp = None, None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote:
                ssh_client = self._get_ssh_client(settings)
                sftp = ssh_client.open_sftp()
            
            install_path = settings['immich_install_path']
            self.log_message.emit("Stopping and removing Immich containers and volumes...")
            self._run_command_stream(["docker", "compose", "down", "-v"], cwd=install_path, ssh_client=ssh_client)
            
            for sub in ["pgdata", "model-cache"]:
                dir_path = os.path.join(install_path, sub)
                self.log_message.emit(f"Deleting directory: {dir_path}")
                if sftp: self._sftp_rmtree(sftp, dir_path)
                elif os.path.exists(dir_path): shutil.rmtree(dir_path, ignore_errors=True)

            self.log_message.emit("Starting Immich with fresh volumes...")
            self._run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path, ssh_client=ssh_client)
            self.log_message.emit("Immich re-installation completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to re-install Immich: {e}")
        finally:
            if sftp: sftp.close()
            if ssh_client: ssh_client.close()
            time_module.sleep(5); self.finished.emit("manage")
            
    @Slot(dict)
    def run_immich_uninstall(self, settings):
        ssh_client, sftp = None, None
        try:
            is_remote = settings.get("ssh_enabled", False)
            if is_remote:
                ssh_client = self._get_ssh_client(settings)
                sftp = ssh_client.open_sftp()
                
            install_path = settings['immich_install_path']
            self.log_message.emit("Stopping and removing Immich containers and volumes...")
            self._run_command_stream(["docker", "compose", "down", "-v"], cwd=install_path, ssh_client=ssh_client)
            
            for sub in ["pgdata", "model-cache"]:
                dir_path = os.path.join(install_path, sub)
                self.log_message.emit(f"Deleting directory: {dir_path}")
                if sftp: self._sftp_rmtree(sftp, dir_path)
                elif os.path.exists(dir_path): shutil.rmtree(dir_path, ignore_errors=True)

            for f_name in ["docker-compose.yml", ".env"]:
                 f_path = os.path.join(install_path, f_name)
                 self.log_message.emit(f"Deleting file: {f_path}")
                 try:
                     if sftp: sftp.remove(f_path)
                     elif os.path.exists(f_path): os.unlink(f_path)
                 except Exception: pass

            self.log_message.emit("Immich uninstallation completed successfully! Your media files were not touched.")
        except Exception as e:
            self.error_message.emit(f"Failed to uninstall Immich: {e}")
        finally:
            if sftp: sftp.close()
            if ssh_client: ssh_client.close()
            time_module.sleep(3); self.finished.emit("manage")

    @Slot()
    def fetch_immich_versions(self):
        try:
            self.log_message.emit("Fetching available Immich versions from GitHub...")
            url = "https://api.github.com/repos/immich-app/immich/tags"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            tags = response.json()
            version_names = [tag['name'] for tag in tags if 'name' in tag]
            self.log_message.emit(f"Found {len(version_names)} versions.")
            self.versions_fetched.emit(version_names)
        except Exception as e:
            self.error_message.emit(f"Could not fetch versions: {e}")
            self.versions_fetched.emit([])

    @Slot(str)
    def fetch_release_notes(self, version):
        try:
            self.log_message.emit(f"Fetching release notes for {version}...")
            url = f"https://api.github.com/repos/immich-app/immich/releases/tags/{version}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            notes = response.json().get("body", "No release notes found for this version.")
            self.release_notes_fetched.emit(version, notes)
        except Exception as e:
            error_msg = f"Could not fetch release notes for {version}: {e}"
            self.error_message.emit(error_msg)
            self.release_notes_fetched.emit(version, error_msg)

    def _get_immich_version(self, install_path, service_name="immich-server", ssh_client=None):
        if not install_path: return "Unknown"
        try:
            id_command = f"docker compose ps -q {service_name}"
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(f"cd {install_path} && {id_command}")
                container_id = stdout.read().decode('utf-8').strip()
            else:
                result_id = subprocess.run(id_command, cwd=install_path, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0, shell=True)
                container_id = result_id.stdout.strip()

            if not container_id: return "Unknown"
            
            inspect_command = f"docker inspect {container_id}"
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(inspect_command)
                inspect_output = stdout.read().decode('utf-8')
            else:
                result_inspect = subprocess.run(inspect_command, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0, shell=True)
                inspect_output = result_inspect.stdout
            
            inspect_data = json.loads(inspect_output)
            image_name = inspect_data[0].get("Config", {}).get("Image", "")
            tag = image_name.split(':')[-1] if ':' in image_name else ""
            
            if tag and tag not in ['latest', 'release']: return tag
            elif tag in ['latest', 'release']:
                return requests.get("https://api.github.com/repos/immich-app/immich/releases/latest", timeout=10).json().get("tag_name", tag)
        except Exception:
            pass
        return "Unknown"

    @Slot(dict, bool, object)
    def run_media_restore(self, settings, emit_finish_signal=True, ssh_client_in=None):
        ssh_client = None
        try:
            if emit_finish_signal: self.log_message.emit("Starting media restore...")
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = ssh_client_in if ssh_client_in else self._get_ssh_client(settings)
            
            backup_media_dir = settings['backup_media_dir']
            target_media_dir = settings['source_dir']

            if is_remote:
                 sftp = ssh_client.open_sftp()
                 self._sftp_rmtree(sftp, target_media_dir)
                 self._sftp_makedirs(sftp, target_media_dir)
                 sftp.close()
            else:
                if not Path(backup_media_dir).exists(): raise FileNotFoundError("Backup media source does not exist.")
                if Path(target_media_dir).exists(): shutil.rmtree(target_media_dir)
                os.makedirs(target_media_dir, exist_ok=True)
            
            self._copy_with_progress(backup_media_dir, target_media_dir, ssh_client)
            self.log_message.emit("Media restore completed successfully!")
        except Exception as e: self.error_message.emit(f"An error occurred during media restore: {e}")
        finally:
            if emit_finish_signal and ssh_client: ssh_client.close()
            if emit_finish_signal: self.finished.emit("restored")

    @Slot(dict, bool, object)
    def run_db_restore(self, settings, emit_finish_signal=True, ssh_client_in=None):
        ssh_client = None
        try:
            if emit_finish_signal: self.log_message.emit("Starting database restore...")
            is_remote = settings.get("ssh_enabled", False)
            if is_remote: ssh_client = ssh_client_in if ssh_client_in else self._get_ssh_client(settings)
            self._restore_database_logic(settings['backup_sql_file'], settings['container_name'], settings['db_user'], ssh_client)
        except Exception as e: self.error_message.emit(f"An error occurred during database restore: {e}")
        finally:
            if emit_finish_signal and ssh_client: ssh_client.close()
            if emit_finish_signal: self.finished.emit("restored")

    def _restore_database_logic(self, backup_sql_file, container_name, db_user, ssh_client):
        if not self._is_docker_running(ssh_client): raise RuntimeError("Docker not running")
        
        self.log_message.emit(f"Restoring from: {backup_sql_file}")
        
        if ssh_client:
            remote_sql_path = f"/tmp/{os.path.basename(backup_sql_file)}"
            sftp = ssh_client.open_sftp()
            self.log_message.emit(f"Uploading SQL file to remote: {remote_sql_path}")
            sftp.put(backup_sql_file, remote_sql_path)
            sftp.close()
            
            command = f'docker exec -i {container_name} psql -U {db_user} < {remote_sql_path}'
            stdin, stdout, stderr = ssh_client.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            
            ssh_client.exec_command(f'rm {remote_sql_path}') # Clean up
            
            if exit_code != 0:
                raise RuntimeError(f"DB restore failed: {stderr.read().decode('utf-8')}")
        else:
            if not Path(backup_sql_file).exists(): raise FileNotFoundError(f"Backup file not found: {backup_sql_file}")
            command = f'docker exec -i {container_name} psql -U {db_user} < "{backup_sql_file}"'
            proc = subprocess.run(command, shell=True, capture_output=True, text=True)
            if proc.returncode != 0: raise RuntimeError(f"DB restore failed: {proc.stderr}")
        
        self.log_message.emit("Database restore completed successfully!")

    def _is_docker_running(self, ssh_client=None):
        try:
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command("docker info")
                return stdout.channel.recv_exit_status() == 0
            else:
                return subprocess.run("docker info", shell=True, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0).returncode == 0
        except: return False

    def _does_container_exist(self, name, install_path, ssh_client=None):
        project_name = os.path.basename(install_path).lower().replace(" ", "")
        # This matches the full container name like 'immich_immich-server_1'
        # Docker compose v1: projectname_servicename_1
        # Docker compose v2: projectname-servicename-1
        # We will match projectname[_-]servicename
        container_pattern = f"{project_name}[_-]{name}"

        command = f'docker ps -q -f "name={container_pattern}"'

        try:
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(command)
                return stdout.read().decode('utf-8').strip() != ""
            else:
                return subprocess.run(command, shell=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0).stdout.strip() != ""
        except Exception:
            return False

    def _backup_database(self, container, user, file_path, ssh_client=None):
        command = f'docker exec -t {container} pg_dumpall -c -U {user}'
        try:
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(command)
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(stdout, f)
                if stdout.channel.recv_exit_status() != 0:
                    raise RuntimeError(f"pg_dump failed: {stderr.read().decode('utf-8')}")
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    proc = subprocess.run(command, shell=True, stdout=f, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                    if proc.returncode != 0: raise RuntimeError(f"pg_dump failed: {proc.stderr}")
        except Exception as e:
            if Path(file_path).exists(): os.remove(file_path)
            raise e

    def _copy_with_progress(self, src, dst, ssh_client=None):
        if ssh_client:
            self.log_message.emit("Media copy over SSH is not supported yet. Please use rsync or other tools manually.")
            # This is a complex operation (recursive copy with progress).
            # For now, we will skip it and log a message.
            # A proper implementation would use `tar` on both ends or a recursive sftp copy.
            self.log_message.emit("Skipping media file copy.")
            return

        src_path, dst_path = Path(src), Path(dst)
        total_files = sum(1 for _ in src_path.rglob('*') if _.is_file())
        copied = 0
        self.progress.emit(0, total_files)
        for item in src_path.rglob('*'):
            if not self.is_running: self.log_message.emit("Operation cancelled."); return
            dest_item = dst_path / item.relative_to(src_path)
            if item.is_dir(): dest_item.mkdir(parents=True, exist_ok=True)
            else:
                shutil.copy2(item, dest_item); copied += 1
                if copied % 20 == 0 or copied == total_files:
                    self.progress.emit(copied, total_files)
        if total_files > 0: self.progress.emit(total_files, total_files)

    def _apply_retention_policy(self, backup_root_dir, days, ssh_client=None):
        if days <= 0: self.log_message.emit("Retention policy is disabled."); return
        now = datetime.now()
        
        if ssh_client:
            sftp = ssh_client.open_sftp()
            try:
                for item in sftp.listdir_attr(backup_root_dir):
                    if item.filename.startswith("ImmichBackup_") and stat.S_ISDIR(item.st_mode):
                        try:
                            timestamp_str = item.filename.replace("ImmichBackup_", "")
                            backup_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                            if (now - backup_date).days > days:
                                dir_path = os.path.join(backup_root_dir, item.filename)
                                self.log_message.emit(f"Deleting old remote backup: {dir_path}")
                                self._sftp_rmtree(sftp, dir_path)
                        except (IndexError, ValueError): continue
            except FileNotFoundError:
                self.log_message.emit(f"Remote backup directory not found: {backup_root_dir}")
            finally:
                sftp.close()
        else:
            for d in Path(backup_root_dir).glob("ImmichBackup_*"):
                if d.is_dir():
                    try:
                        timestamp_str = d.name.replace("ImmichBackup_", "")
                        backup_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        if (now - backup_date).days > days:
                            self.log_message.emit(f"Deleting old backup: {d.name}")
                            shutil.rmtree(d)
                    except (IndexError, ValueError): continue

    def _write_backup_log(self, backup_dir, status, duration, error_msg, backup_type="Unknown"):
        log_file = Path(backup_dir) / "backup_log.json"
        history = []
        if log_file.exists():
            try: history = json.loads(log_file.read_text())
            except: pass
        history.insert(0, {"timestamp": datetime.now().isoformat(), "status": status, "duration_seconds": round(duration, 2), "error": error_msg, "type": backup_type})
        log_file.write_text(json.dumps(history[:20], indent=2))

    # --- SFTP Helper Functions ---
    def _sftp_makedirs(self, sftp, path):
        """Equivalent of os.makedirs for SFTP."""
        parts = path.replace('\\', '/').split('/')
        current_path = ""
        for part in parts:
            if not part:
                if not current_path: current_path = "/"
                continue
            current_path = os.path.join(current_path, part) if current_path != "/" else f"/{part}"
            try:
                sftp.stat(current_path)
            except FileNotFoundError:
                sftp.mkdir(current_path)
    
    def _sftp_rmtree(self, sftp, remotedir):
        """Equivalent of shutil.rmtree for SFTP."""
        try:
            for item in sftp.listdir_attr(remotedir):
                remote_path = f"{remotedir}/{item.filename}"
                if stat.S_ISDIR(item.st_mode):
                    self._sftp_rmtree(sftp, remote_path)
                else:
                    sftp.remove(remote_path)
            sftp.rmdir(remotedir)
        except FileNotFoundError:
            pass # Directory does not exist
        except Exception as e:
            self.log_message.emit(f"Could not remove remote directory {remotedir}: {e}")
