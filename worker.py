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

    @Slot()
    def stop(self): self.is_running = False
    
    @Slot(str)
    def fetch_docker_status(self, install_path):
        status_dict = {}
        version = "Unknown"
        try:
            expected_services = ['immich-server', 'immich-microservices', 'immich-machine-learning', 'immich-postgres', 'redis']
            status_dict = {name.replace('-', '_'): 'stopped' for name in expected_services}

            if not self._is_docker_running(): raise RuntimeError("Docker is not running")
            if not install_path or not Path(install_path).exists(): raise RuntimeError("Immich install path not set or invalid")

            version = self._get_immich_version(install_path)

            project_name = Path(install_path).name.lower().replace(" ", "")
            command = ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project_name}", "--format", "{{json .}}"]
            
            result = subprocess.run(command, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)

            for line in result.stdout.strip().splitlines():
                if not line: continue
                try:
                    container_info = json.loads(line)
                    if not isinstance(container_info, dict): continue
                except json.JSONDecodeError:
                    continue
                
                # --- FINAL ROBUST LABEL PARSING ---
                labels_data = container_info.get("Labels", {})
                labels_dict = {}

                if isinstance(labels_data, dict):
                    labels_dict = labels_data
                elif isinstance(labels_data, str):
                    try:
                        # Use a positive lookahead regex to split on commas that are followed by a key= pattern.
                        # This prevents splitting on commas within a value (e.g., in 'depends_on').
                        items = re.split(r',(?=[\w\.-]+=)', labels_data)
                        labels_dict = dict(item.split('=', 1) for item in items)
                    except ValueError:
                        self.log_message.emit(f"Warning: Could not parse labels string: {labels_data}")
                        labels_dict = {}
                # --- END OF FIX ---

                # Handle the 'database' service which is not 'immich-postgres'
                service_name = labels_dict.get("com.docker.compose.service")
                if service_name == "database":
                    service_name = "immich-postgres"

                state = container_info.get("State")

                if service_name in expected_services:
                    status_dict[service_name.replace('-', '_')] = state

        except Exception as e:
            self.log_message.emit(f"Could not fetch Docker status: {e}")
            for key in status_dict: status_dict[key] = 'unknown'
        finally:
            payload = {"version": version, "containers": status_dict}
            self.docker_status_fetched.emit(payload)

    @Slot(str, str, str, str, int)
    def run_backup(self, source_dir, backup_root_dir, container_name, db_user, retention_days):
        start_time, status, error_msg = time_module.time(), "failure", ""
        try:
            self.log_message.emit("Starting full backup process...")
            if not self._is_docker_running(): raise RuntimeError("Docker is not running")
            if not self._does_container_exist(container_name): raise RuntimeError(f"Container '{container_name}' not found")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(backup_root_dir) / f"ImmichBackup_{timestamp}"
            os.makedirs(backup_path / "media", exist_ok=True); os.makedirs(backup_path / "database", exist_ok=True)
            
            self.log_message.emit("Backing up database...")
            db_file = backup_path / "database" / f"immich_db_{timestamp}.sql"
            self._backup_database(container_name, db_user, str(db_file))
            if not self.is_running: return

            self.log_message.emit("Backing up media files...")
            self._copy_with_progress(source_dir, str(backup_path / "media"))
            if not self.is_running: return

            self.log_message.emit("Cleaning up old backups..."); self._apply_retention_policy(backup_root_dir, retention_days)
            self.log_message.emit("\nFull backup process completed successfully!"); status = "success"
        except Exception as e:
            error_msg = str(e); self.error_message.emit(f"An error occurred during full backup: {error_msg}")
        finally:
            duration = time_module.time() - start_time
            self._write_backup_log(backup_root_dir, status, duration, error_msg, "Full")
            self.finished.emit(status)

    @Slot(str, str, str, int)
    def run_db_backup(self, backup_root_dir, container_name, db_user, retention_days):
        start_time, status, error_msg = time_module.time(), "failure", ""
        try:
            self.log_message.emit("Starting database-only backup...")
            if not self._is_docker_running(): raise RuntimeError("Docker is not running")
            if not self._does_container_exist(container_name): raise RuntimeError(f"Container '{container_name}' not found")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(backup_root_dir) / f"ImmichBackup_{timestamp}"
            os.makedirs(backup_path / "database", exist_ok=True)
            
            self.log_message.emit("Backing up database...")
            db_file = backup_path / "database" / f"immich_db_{timestamp}.sql"
            self._backup_database(container_name, db_user, str(db_file))
            if not self.is_running: return

            self.log_message.emit("Cleaning up old backups..."); self._apply_retention_policy(backup_root_dir, retention_days)
            self.log_message.emit("\nDatabase backup completed successfully!"); status = "success"
        except Exception as e:
            error_msg = str(e); self.error_message.emit(f"An error occurred during database backup: {error_msg}")
        finally:
            duration = time_module.time() - start_time
            self._write_backup_log(backup_root_dir, status, duration, error_msg, "Database Only")
            self.finished.emit(status)

    @Slot(str, str, int)
    def run_media_backup(self, source_dir, backup_root_dir, retention_days):
        start_time, status, error_msg = time_module.time(), "failure", ""
        try:
            self.log_message.emit("Starting media-only backup...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(backup_root_dir) / f"ImmichBackup_{timestamp}"
            os.makedirs(backup_path / "media", exist_ok=True)
            
            self.log_message.emit("Backing up media files...")
            self._copy_with_progress(source_dir, str(backup_path / "media"))
            if not self.is_running: return

            self.log_message.emit("Cleaning up old backups..."); self._apply_retention_policy(backup_root_dir, retention_days)
            self.log_message.emit("\nMedia backup completed successfully!"); status = "success"
        except Exception as e:
            error_msg = str(e); self.error_message.emit(f"An error occurred during media backup: {error_msg}")
        finally:
            duration = time_module.time() - start_time
            self._write_backup_log(backup_root_dir, status, duration, error_msg, "Media Only")
            self.finished.emit(status)

    @Slot(str, str, str, str, str)
    def run_full_restore(self, backup_media_dir, target_media_dir, backup_sql_file, container_name, db_user):
        try:
            self.log_message.emit("Starting full restore process..."); self.progress.emit(0, 100)
            if not self.is_running: return

            self.log_message.emit("--- Step 1 of 2: Restoring media ---")
            if not Path(backup_media_dir).exists(): raise FileNotFoundError("Backup media source does not exist.")
            if Path(target_media_dir).exists(): shutil.rmtree(target_media_dir)
            os.makedirs(target_media_dir, exist_ok=True)
            self._copy_with_progress(backup_media_dir, target_media_dir); self.progress.emit(50, 100)
            self.log_message.emit("Media restore completed successfully!")

            self.log_message.emit("\n--- Step 2 of 2: Restoring database ---")
            self._restore_database_logic(backup_sql_file, container_name, db_user)
            self.progress.emit(100, 100); self.log_message.emit("\nFull restore process finished.")
        except Exception as e:
            self.error_message.emit(f"An error occurred during full restore: {e}")
        finally:
            self.finished.emit("restored")

    def run_command_stream(self, command, cwd):
        self.log_message.emit(f"Running command: {' '.join(command)}")
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
        for line in process.stdout:
            self.log_message.emit(line.strip())
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {process.returncode}")

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

    @Slot(str, str, str, str, bool)
    def run_immich_install(self, install_path, version, db_pass, upload_path, is_latest):
        try:
            p_install = Path(install_path)
            p_install.mkdir(exist_ok=True)
            
            compose_content = self._fetch_github_file(version, "docker-compose.yml", is_latest)
            env_content = self._fetch_github_file(version, "example.env", is_latest)
            
            self.log_message.emit("Writing docker-compose.yml...")
            (p_install / "docker-compose.yml").write_text(compose_content)

            self.log_message.emit("Configuring and writing .env file...")
            p_parent_media = Path(upload_path)
            posix_parent_path = p_parent_media.as_posix()
            self.log_message.emit(f"Setting '.env' UPLOAD_LOCATION to parent media directory: {posix_parent_path}")
            
            updates = {"UPLOAD_LOCATION": posix_parent_path, "DB_PASSWORD": db_pass, "POSTGRES_PASSWORD": db_pass}
            if not is_latest: updates["IMMICH_VERSION"] = version
            updated_env = self._update_env_file_content(env_content, updates)
            (p_install / ".env").write_text(updated_env)

            self.log_message.emit("Ensuring required media subdirectories and integrity files exist...")
            required_subdirs = ["upload", "thumbs", "profile", "encoded-video", "library", "backups"]
            for subdir in required_subdirs:
                full_path = p_parent_media / subdir
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    (full_path / ".immich").touch(exist_ok=True)
                    self.log_message.emit(f"  ✓ Path and integrity file ready: {full_path}")
                except Exception as e:
                    self.log_message.emit(f"  - WARNING: Could not prepare subdirectory '{full_path}'. Error: {e}")

            self.log_message.emit("Adding a 5-second delay for file system synchronization...")
            time_module.sleep(5)

            self.run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path)
            self.log_message.emit("Immich installation completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to install Immich: {e}")
        finally:
            time_module.sleep(5); self.finished.emit("manage")

    def _perform_update_steps(self, install_path, version, is_latest):
        self.log_message.emit("Stopping Immich containers..."); self.run_command_stream(["docker", "compose", "down"], cwd=install_path)
        
        new_compose = self._fetch_github_file(version, "docker-compose.yml", is_latest)
        new_env_template = self._fetch_github_file(version, "example.env", is_latest)
        
        self.log_message.emit("Writing new docker-compose.yml...");
        (Path(install_path) / "docker-compose.yml").write_text(new_compose)

        self.log_message.emit("Preserving settings from old .env file...")
        old_env_path = Path(install_path) / ".env"
        old_settings = {}
        if old_env_path.exists():
            with open(old_env_path, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith("#"):
                        key, val = line.strip().split('=', 1)
                        old_settings[key] = val
        
        if is_latest: old_settings.pop("IMMICH_VERSION", None)
        else: old_settings["IMMICH_VERSION"] = version
        
        updated_env = self._update_env_file_content(new_env_template, old_settings)
        old_env_path.write_text(updated_env)

        self.log_message.emit("Pulling new Docker images..."); self.run_command_stream(["docker", "compose", "pull"], cwd=install_path)
        self.log_message.emit("Recreating containers with the new version..."); self.run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path)
        self.log_message.emit(f"Update/rollback to version {version} completed.")
        
    @Slot(str, str, bool)
    def run_immich_update(self, install_path, version, is_latest):
        try:
            self._perform_update_steps(install_path, version, is_latest)
            self.log_message.emit("Immich update completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to update Immich: {e}")
        finally:
            time_module.sleep(5); self.finished.emit("manage")
            
    @Slot(str, str, str, str, str, bool)
    def run_safe_update(self, install_path, old_version, new_version, container_name, db_user, is_latest):
        temp_backup_dir = Path(install_path) / "immichsafe_temp"
        temp_backup_path = None
        try:
            self.log_message.emit("--- Starting Safe Update Process ---")
            
            self.log_message.emit("Step 1: Creating temporary database backup...")
            if not self._does_container_exist(container_name):
                 raise RuntimeError(f"Database container '{container_name}' is not running. Cannot create backup.")

            temp_backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_backup_path = temp_backup_dir / f"pre_update_backup_{timestamp}.sql"
            self._backup_database(container_name, db_user, str(temp_backup_path))
            self.log_message.emit("Temporary backup created successfully.")

            self.log_message.emit(f"Step 2: Attempting to update from {old_version} to {new_version}...")
            self._perform_update_steps(install_path, new_version, is_latest)
            
            self.log_message.emit("Step 3: Performing post-update health check...")
            time_module.sleep(15) 
            if not self._health_check(install_path):
                raise RuntimeError("Health check failed after update. Services did not start correctly.")
            
            self.log_message.emit("Health check passed! Update successful.")
            self.log_message.emit("--- Safe Update Process Completed Successfully ---")

        except Exception as e:
            self.error_message.emit(f"Update failed: {e}. Initiating rollback...")
            try:
                self.log_message.emit(f"--- Rolling back to version {old_version} ---")
                self._perform_update_steps(install_path, old_version, False)
                
                self.log_message.emit("Restoring database from temporary backup...")
                if temp_backup_path and temp_backup_path.exists():
                    self._restore_database_logic(str(temp_backup_path), container_name, db_user)
                else:
                    self.log_message.emit("Warning: Could not find temporary backup to restore.")
                self.log_message.emit("Rollback successful. Your system has been restored.")
            except Exception as rollback_e:
                self.error_message.emit(f"CRITICAL: ROLLBACK FAILED. {rollback_e}. Manual intervention may be required.")
        finally:
            if temp_backup_dir.exists():
                self.log_message.emit("Cleaning up temporary backup files.")
                shutil.rmtree(temp_backup_dir)
            time_module.sleep(5); self.finished.emit("manage")

    def _health_check(self, install_path):
        self.log_message.emit("Checking container status...")
        return self._get_immich_version(install_path) != "Unknown"

    @Slot(str, str)
    def run_immich_action(self, install_path, action):
        try:
            self.run_command_stream(["docker", "compose"] + action.split(), cwd=install_path)
            self.log_message.emit(f"Immich {action} command finished.")
        except Exception as e:
            self.error_message.emit(f"Failed to {action} Immich: {e}")
        finally:
            time_module.sleep(3); self.finished.emit("manage")
            
    @Slot(str)
    def run_immich_reinstall(self, install_path):
        try:
            self.log_message.emit("Stopping and removing Immich containers and volumes...")
            self.run_command_stream(["docker", "compose", "down", "-v"], cwd=install_path)
            
            for sub in ["pgdata", "model-cache"]:
                if (d := Path(install_path) / sub).exists():
                    self.log_message.emit(f"Deleting directory: {d}")
                    shutil.rmtree(d, ignore_errors=True)

            self.log_message.emit("Starting Immich with fresh volumes...")
            self.run_command_stream(["docker", "compose", "up", "-d"], cwd=install_path)
            self.log_message.emit("Immich re-installation completed successfully!")
        except Exception as e:
            self.error_message.emit(f"Failed to re-install Immich: {e}")
        finally:
            time_module.sleep(5); self.finished.emit("manage")
            
    @Slot(str)
    def run_immich_uninstall(self, install_path):
        try:
            self.log_message.emit("Stopping and removing Immich containers and volumes...")
            self.run_command_stream(["docker", "compose", "down", "-v"], cwd=install_path)
            
            p_install = Path(install_path)
            for sub in ["pgdata", "model-cache"]:
                if (d := p_install / sub).exists():
                    self.log_message.emit(f"Deleting directory: {d}")
                    shutil.rmtree(d, ignore_errors=True)

            for f_name in ["docker-compose.yml", ".env"]:
                 if (f_path := p_install / f_name).exists():
                      self.log_message.emit(f"Deleting file: {f_path}")
                      f_path.unlink()

            self.log_message.emit("Immich uninstallation completed successfully! Your media files were not touched.")
        except Exception as e:
            self.error_message.emit(f"Failed to uninstall Immich: {e}")
        finally:
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

    def _get_immich_version(self, install_path, service_name="immich-server"):
        if not install_path or not Path(install_path).exists(): return "Unknown"
        try:
            id_command = ["docker", "compose", "ps", "-q", service_name]
            result_id = subprocess.run(id_command, cwd=install_path, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
            if not (container_id := result_id.stdout.strip()): return "Unknown"

            inspect_command = ["docker", "inspect", container_id]
            result_inspect = subprocess.run(inspect_command, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
            
            try:
                inspect_data = json.loads(result_inspect.stdout)
            except json.JSONDecodeError:
                return "Unknown"

            if not isinstance(inspect_data, list) or not inspect_data or not isinstance(inspect_data[0], dict):
                return "Unknown"
                
            image_name = inspect_data[0].get("Config", {}).get("Image", "")
            tag = ""
            if ':' in image_name:
                tag = image_name.split(':')[-1]
            
            if tag and tag not in ['latest', 'release']:
                return tag
            elif tag in ['latest', 'release']:
                url = "https://api.github.com/repos/immich-app/immich/releases/latest"
                response = requests.get(url, timeout=10); response.raise_for_status()
                return response.json().get("tag_name", tag)
        except (subprocess.CalledProcessError, FileNotFoundError, requests.RequestException):
            pass
        return "Unknown"

    @Slot(str, str, bool)
    def run_media_restore(self, backup_media_dir, target_media_dir, emit_finish_signal=True):
        try:
            if emit_finish_signal: self.log_message.emit("Starting media restore...")
            p_backup = Path(backup_media_dir)
            p_target = Path(target_media_dir)
            if not p_backup.exists(): raise FileNotFoundError("Backup media source does not exist.")
            if p_target.exists(): shutil.rmtree(p_target)
            p_target.mkdir(parents=True, exist_ok=True)
            self._copy_with_progress(str(p_backup), str(p_target))
            self.log_message.emit("Media restore completed successfully!")
        except Exception as e: self.error_message.emit(f"An error occurred during media restore: {e}")
        finally:
            if emit_finish_signal: self.finished.emit("restored")

    def _restore_database_logic(self, backup_sql_file, container_name, db_user):
        if not self._is_docker_running(): raise RuntimeError("Docker not running")
        if not self._does_container_exist(container_name): raise RuntimeError(f"Container '{container_name}' not found")
        if not Path(backup_sql_file).exists(): raise FileNotFoundError(f"Backup file not found: {backup_sql_file}")
        self.log_message.emit(f"Restoring from: {backup_sql_file}")
        command = f'docker exec -i {container_name} psql -U {db_user} < "{backup_sql_file}"'
        proc = subprocess.run(command, shell=True, capture_output=True, text=True)
        if proc.returncode != 0: raise RuntimeError(f"DB restore failed: {proc.stderr}")
        self.log_message.emit("Database restore completed successfully!")
        
    @Slot(str, str, str, bool)
    def run_db_restore(self, backup_sql_file, container_name, db_user, emit_finish_signal=True):
        try:
            if emit_finish_signal: self.log_message.emit("Starting database restore...")
            self._restore_database_logic(backup_sql_file, container_name, db_user)
        except Exception as e: self.error_message.emit(f"An error occurred during database restore: {e}")
        finally:
            if emit_finish_signal: self.finished.emit("restored")

    def _is_docker_running(self):
        try: return subprocess.run("docker info", shell=True, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0).returncode == 0
        except: return False

    def _does_container_exist(self, name):
        return subprocess.run(f'docker ps -q -f name="^{name}$"', shell=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0).stdout.strip() != ""

    def _backup_database(self, container, user, file_path):
        command = f'docker exec -t {container} pg_dumpall -c -U {user}'
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                proc = subprocess.run(command, shell=True, stdout=f, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                if proc.returncode != 0: raise RuntimeError(f"pg_dump failed: {proc.stderr}")
        except Exception as e:
            if Path(file_path).exists(): os.remove(file_path)
            raise e
            
    def _copy_with_progress(self, src, dst):
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

    def _apply_retention_policy(self, backup_root_dir, days):
        if days <= 0: self.log_message.emit("Retention policy is disabled."); return
        now = datetime.now()
        for d in Path(backup_root_dir).glob("ImmichBackup_*"):
            if d.is_dir():
                try:
                    # Correctly parse the full timestamp from the backup folder name
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

