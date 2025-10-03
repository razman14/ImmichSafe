import sys
import os
import json
from pathlib import Path
import webbrowser
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QLabel, QFormLayout, QSpinBox, QMessageBox, QComboBox,
    QSystemTrayIcon, QMenu, QGroupBox, QCheckBox, QStyle, QFrame,
    QGridLayout, QListWidget, QListWidgetItem, QTimeEdit
)
from PySide6.QtCore import QThread, Signal, QTimer, QTime, Qt
from PySide6.QtGui import QIcon, QAction, QColor

from config import APP_NAME, APP_VERSION, CONFIG_FILE, REG_KEY_PATH, IS_WINDOWS
from worker import Worker
from theme import get_stylesheet, get_system_theme

if IS_WINDOWS:
    import winreg

class MainWindow(QMainWindow):
    backup_requested = Signal(str, str, str, str, int)
    db_backup_requested = Signal(str, str, str, int)
    media_backup_requested = Signal(str, str, int)
    media_restore_requested = Signal(str, str)
    db_restore_requested = Signal(str, str, str)
    full_restore_requested = Signal(str, str, str, str, str)
    install_requested = Signal(str, str, str, str, bool)
    update_requested = Signal(str, str, bool)
    safe_update_requested = Signal(str, str, str, str, str, bool)
    action_requested = Signal(str, str)
    reinstall_requested = Signal(str)
    uninstall_requested = Signal(str)
    version_fetch_requested = Signal()
    docker_status_requested = Signal(str)
    release_notes_requested = Signal(str)
    ready_to_show = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setGeometry(100, 100, 850, 700)
        self.setMinimumSize(700, 600)
        self.is_task_running = False
        self.current_immich_version = "Unknown"
        self.latest_version = None
        self.is_initial_load = True
        self.settings = self.load_settings()
        self.backup_settings_dirty = False
        self.app_settings_dirty = False
        self.previous_tab_index = 0

        self.thread, self.worker = QThread(), Worker()
        self.worker.moveToThread(self.thread)
        self.backup_requested.connect(self.worker.run_backup)
        self.db_backup_requested.connect(self.worker.run_db_backup)
        self.media_backup_requested.connect(self.worker.run_media_backup)
        self.media_restore_requested.connect(lambda m, t: self.worker.run_media_restore(m, t, True))
        self.db_restore_requested.connect(lambda f, c, u: self.worker.run_db_restore(f, c, u, True))
        self.full_restore_requested.connect(self.worker.run_full_restore)
        self.install_requested.connect(self.worker.run_immich_install)
        self.update_requested.connect(self.worker.run_immich_update)
        self.safe_update_requested.connect(self.worker.run_safe_update)
        self.action_requested.connect(self.worker.run_immich_action)
        self.reinstall_requested.connect(self.worker.run_immich_reinstall)
        self.uninstall_requested.connect(self.worker.run_immich_uninstall)
        self.version_fetch_requested.connect(self.worker.fetch_immich_versions)
        self.docker_status_requested.connect(self.worker.fetch_docker_status)
        self.release_notes_requested.connect(self.worker.fetch_release_notes)
        self.worker.log_message.connect(self.log)
        self.worker.error_message.connect(self.log_error)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.versions_fetched.connect(self.populate_versions_combo)
        self.worker.docker_status_fetched.connect(self.update_home_dashboard)
        self.worker.release_notes_fetched.connect(self.display_release_notes)
        self.thread.start()
        
        self.init_ui()
        self.init_tray_icon()
        self.init_scheduler()
        
        self.populate_restore_dropdown()
        self.apply_theme()
        self.refresh_home_tab()
        self.update_manage_tab_state()
        self.version_fetch_requested.emit()

    def load_settings(self):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "source_dir": "", "backup_dir": "", "retention_days": 7, 
                "container_name": "immich_postgres", "db_user": "postgres", 
                "start_with_windows": False, "start_minimized": False, "theme": "system",
                "schedule_enabled": False, "schedule_frequency": "Daily", 
                "schedule_time": "02:00", "schedule_day": "Monday", 
                "schedule_day_of_month": 1, "last_auto_backup_ts": 0,
                "immich_install_path": "", "schedule_backup_type": "Full Backup"
            }
    
    def save_settings(self):
        with open(CONFIG_FILE, 'w') as f: json.dump(self.settings, f, indent=4)
        self.log("Settings saved.")

    def apply_theme(self):
        theme = self.settings.get('theme', 'system')
        if theme == 'system': theme = get_system_theme()
        self.setStyleSheet(get_stylesheet(theme))
        self.refresh_home_tab()

    def init_scheduler(self):
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.timeout.connect(self.check_for_scheduled_backup)
        self.scheduler_timer.start(60 * 1000)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)
        
    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        self.setCentralWidget(main_widget)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        self.tabs.addTab(self.create_home_tab(), "Home")
        self.tabs.addTab(self.create_backup_tab(), "Backup")
        self.tabs.addTab(self.create_restore_tab(), "Restore")
        self.tabs.addTab(self.create_manage_tab(), "Manage")
        self.tabs.addTab(self.create_settings_tab(), "Settings")
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        if self.previous_tab_index == 1 and self.backup_settings_dirty:
            if not self.prompt_to_save_changes("Backup"):
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(self.previous_tab_index)
                self.tabs.blockSignals(False)
                return
        elif self.previous_tab_index == 4 and self.app_settings_dirty:
            if not self.prompt_to_save_changes("Application"):
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(self.previous_tab_index)
                self.tabs.blockSignals(False)
                return
        
        self.previous_tab_index = index
        
        if index == 0: self.refresh_home_tab()
        elif index == 1: self.refresh_backup_history()
        elif index == 2: self.populate_restore_dropdown()
        elif index == 3: self.update_manage_tab_state()
        
    def _create_status_panel(self, name):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(frame)
        name_label = QLabel(f"<b>{name.replace('_', ' ').title()}</b>")
        status_label = QLabel("Unknown")
        status_label.setAlignment(Qt.AlignRight)
        layout.addWidget(name_label)
        layout.addWidget(status_label)
        self.container_status_labels[name] = status_label
        return frame

    def create_home_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 20, 30, 20)
        
        self.version_status_label = QLabel("Checking version...")
        self.version_status_label.setVisible(False)
        self.version_status_label.setAlignment(Qt.AlignCenter)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_home_tab)
        
        status_header = QLabel("Container Status")
        status_header.setObjectName("header")
        
        self.container_grid = QGridLayout()
        self.container_grid.setSpacing(10)
        self.container_status_labels = {}
        
        containers = ['immich_server', 'immich_microservices', 'immich_machine_learning', 'immich_postgres', 'redis']
        for i, name in enumerate(containers):
            row, col = divmod(i, 2)
            panel = self._create_status_panel(name)
            self.container_grid.addWidget(panel, row, col)

        layout.addWidget(self.version_status_label)
        layout.addSpacing(10)
        header_layout = QHBoxLayout()
        header_layout.addWidget(status_header)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)
        layout.addLayout(self.container_grid)
        layout.addSpacing(20)

        # Countdown timer UI
        schedule_group = QGroupBox("Next Scheduled Backup")
        schedule_layout = QVBoxLayout(schedule_group)
        self.countdown_label = QLabel("Scheduler is disabled.")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setObjectName("header")
        schedule_layout.addWidget(self.countdown_label)
        layout.addWidget(schedule_group)

        layout.addStretch()
        return tab
        
    def create_backup_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 10, 15, 10)
        
        top_layout = QHBoxLayout()
        left_column = QVBoxLayout()
        right_column = QVBoxLayout()
        top_layout.addLayout(left_column, 2)
        top_layout.addLayout(right_column, 1)
        
        paths_group = QGroupBox("Backup Destination")
        paths_layout = QFormLayout(paths_group)
        self.backup_dir_edit, backup_btn = self._create_path_selector("Select Backup Destination", self.settings.get("backup_dir", ""))
        paths_layout.addRow("Backup Folder:", self._create_hbox(self.backup_dir_edit, backup_btn))
        left_column.addWidget(paths_group)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 10, 0, 10)
        self.backup_media_button = QPushButton("Media Only")
        self.backup_db_button = QPushButton("Database Only")
        self.backup_full_button = QPushButton("Backup All")
        self.backup_full_button.setObjectName("backup_button")
        actions_layout.addWidget(self.backup_media_button)
        actions_layout.addWidget(self.backup_db_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self.backup_full_button)
        self.backup_media_button.clicked.connect(self.start_media_backup)
        self.backup_db_button.clicked.connect(self.start_db_backup)
        self.backup_full_button.clicked.connect(self.start_full_backup)
        left_column.addLayout(actions_layout)

        settings_group = QGroupBox("Backup Settings")
        settings_layout = QFormLayout(settings_group)
        self.setting_retention_days = QSpinBox()
        self.setting_retention_days.setRange(0, 3650)
        self.setting_retention_days.setSuffix(" days (0 to disable)")
        settings_layout.addRow("Backup Retention:", self.setting_retention_days)
        self.setting_container_name = QLineEdit()
        settings_layout.addRow("Postgres Container Name:", self.setting_container_name)
        self.setting_db_user = QLineEdit()
        settings_layout.addRow("Postgres User:", self.setting_db_user)
        left_column.addWidget(settings_group)
        
        schedule_group = QGroupBox("Scheduled Backups")
        schedule_layout = QFormLayout(schedule_group)
        self.schedule_enabled_check = QCheckBox("Enable automatic backups")
        self.schedule_enabled_check.toggled.connect(self.toggle_schedule_controls)
        schedule_layout.addRow(self.schedule_enabled_check)
        self.schedule_time_edit = QTimeEdit()
        self.schedule_time_edit.setDisplayFormat("HH:mm")
        schedule_layout.addRow("Time:", self.schedule_time_edit)
        self.schedule_freq_combo = QComboBox()
        self.schedule_freq_combo.addItems(["Daily", "Weekly", "Monthly"])
        self.schedule_freq_combo.currentTextChanged.connect(self.update_schedule_day_visibility)
        schedule_layout.addRow("Frequency:", self.schedule_freq_combo)
        self.schedule_type_combo = QComboBox()
        self.schedule_type_combo.addItems(["Full Backup", "Media Only", "Database Only"])
        schedule_layout.addRow("Backup Type:", self.schedule_type_combo)
        self.schedule_day_combo = QComboBox()
        self.schedule_day_combo.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        self.schedule_day_label = QLabel("Day of Week:")
        schedule_layout.addRow(self.schedule_day_label, self.schedule_day_combo)
        self.schedule_dom_spin = QSpinBox()
        self.schedule_dom_spin.setRange(1, 31)
        self.schedule_dom_label = QLabel("Day of Month:")
        schedule_layout.addRow(self.schedule_dom_label, self.schedule_dom_spin)
        left_column.addWidget(schedule_group)

        self.save_backup_settings_btn = QPushButton("Save Backup Settings")
        self.save_backup_settings_btn.clicked.connect(self.collect_and_save_settings)
        left_column.addWidget(self.save_backup_settings_btn)
        left_column.addStretch()

        history_group = QGroupBox("Recent Backups")
        history_layout = QVBoxLayout(history_group)
        self.history_list = QListWidget()
        self.history_list.setWordWrap(True)
        history_layout.addWidget(self.history_list)
        right_column.addWidget(history_group)
        
        self.backup_progress_bar, self.backup_log_console = self._create_progress_log_widgets()

        layout.addLayout(top_layout)
        layout.addWidget(self.backup_progress_bar)
        layout.addWidget(self.backup_log_console)

        self._connect_backup_setting_signals()
        self.load_backup_settings_to_ui()
        self.toggle_schedule_controls(self.schedule_enabled_check.isChecked())
        self.update_schedule_day_visibility(self.schedule_freq_combo.currentText())

        return tab

    def create_restore_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 20, 30, 20)
        restore_source_layout = QFormLayout()
        self.restore_backup_dir_edit, restore_browse_btn = self._create_path_selector("Select Backup Folder", self.settings.get("backup_dir", ""))
        restore_source_layout.addRow("Backup Folder:", self._create_hbox(self.restore_backup_dir_edit, restore_browse_btn))
        restore_browse_btn.clicked.connect(self.select_restore_source_and_refresh)
        self.restore_selection_combo = QComboBox()
        self.restore_selection_combo.currentIndexChanged.connect(self.on_restore_selection_changed)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.populate_restore_dropdown)
        restore_source_layout.addRow("Available Backups:", self._create_hbox(self.restore_selection_combo, refresh_button))
        self.restore_info_label = QLabel("Select a backup to see details.")
        self.restore_info_label.setAlignment(Qt.AlignCenter)
        self.restore_info_label.setStyleSheet("color: #8a8d91; font-style: italic; margin-top: 10px;")
        button_layout = QHBoxLayout()
        self.restore_full_button = QPushButton("Full Restore")
        self.restore_full_button.setObjectName("restore_button")
        self.restore_media_button = QPushButton("Media Only")
        self.restore_db_button = QPushButton("Database Only")
        for btn in [self.restore_full_button, self.restore_media_button, self.restore_db_button]:
            btn.setEnabled(False)
        self.restore_full_button.clicked.connect(self.start_full_restore)
        self.restore_media_button.clicked.connect(self.start_media_restore)
        self.restore_db_button.clicked.connect(self.start_db_restore)
        button_layout.addWidget(self.restore_media_button)
        button_layout.addWidget(self.restore_db_button)
        button_layout.addStretch()
        button_layout.addWidget(self.restore_full_button)
        self.restore_progress_bar, self.restore_log_console = self._create_progress_log_widgets()
        layout.addLayout(restore_source_layout)
        layout.addWidget(self.restore_info_label)
        layout.addSpacing(20)
        layout.addLayout(button_layout)
        layout.addSpacing(20)
        layout.addWidget(self.restore_progress_bar)
        layout.addWidget(self.restore_log_console)
        return tab
    
    def create_manage_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 20, 30, 20)
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        self.manage_install_path_label = QLabel(self.settings.get("immich_install_path") or "Not Set")
        form_layout.addRow("Immich Installation Path:", self.manage_install_path_label)

        self.manage_version_combo = QComboBox()
        self.manage_version_combo.addItem("Fetching versions...")
        self.manage_version_combo.currentTextChanged.connect(self.update_version_button_text)
        refresh_versions_btn = QPushButton("Refresh List")
        refresh_versions_btn.clicked.connect(self.version_fetch_requested.emit)
        self.view_release_notes_btn = QPushButton("View Notes")
        self.view_release_notes_btn.clicked.connect(self.request_release_notes)
        form_layout.addRow("Target Version:", self._create_hbox(self.manage_version_combo, self.view_release_notes_btn, refresh_versions_btn))

        self.manage_db_pass_edit = QLineEdit("postgres")
        self.manage_db_pass_edit.setPlaceholderText("Default: postgres")
        form_layout.addRow("Postgres Password:", self.manage_db_pass_edit)
        
        main_action_layout = QHBoxLayout()
        self.manage_install_update_button = QPushButton("Install")
        self.manage_install_update_button.setObjectName("manage_button")
        self.manage_install_update_button.clicked.connect(self.start_install_or_update)
        main_action_layout.addWidget(self.manage_install_update_button)
        
        self.safe_update_checkbox = QCheckBox("Perform Safe Update (backup & rollback on failure)")
        self.safe_update_checkbox.setChecked(True)

        control_buttons_layout = QHBoxLayout()
        self.manage_start_button = QPushButton("Start")
        self.manage_start_button.clicked.connect(lambda: self.start_manage_action("up -d"))
        self.manage_stop_button = QPushButton("Stop")
        self.manage_stop_button.clicked.connect(lambda: self.start_manage_action("stop"))
        self.manage_restart_button = QPushButton("Restart")
        self.manage_restart_button.clicked.connect(lambda: self.start_manage_action("restart"))
        self.open_immich_button = QPushButton("Open Immich Web")
        self.open_immich_button.clicked.connect(self.open_immich_web)
        control_buttons_layout.addWidget(self.manage_start_button)
        control_buttons_layout.addWidget(self.manage_stop_button)
        control_buttons_layout.addWidget(self.manage_restart_button)
        control_buttons_layout.addStretch()
        control_buttons_layout.addWidget(self.open_immich_button)

        danger_zone_layout = QHBoxLayout()
        self.reinstall_button = QPushButton("Re-install")
        self.reinstall_button.setObjectName("restore_button")
        self.reinstall_button.clicked.connect(self.start_reinstall)
        self.uninstall_button = QPushButton("Uninstall Immich")
        self.uninstall_button.setObjectName("restore_button")
        self.uninstall_button.clicked.connect(self.start_uninstall)
        danger_zone_layout.addStretch()
        danger_zone_layout.addWidget(self.reinstall_button)
        danger_zone_layout.addWidget(self.uninstall_button)

        self.manage_log_console = QTextEdit()
        self.manage_log_console.setReadOnly(True)
        
        layout.addLayout(form_layout)
        layout.addSpacing(10)
        layout.addLayout(main_action_layout)
        layout.addWidget(self.safe_update_checkbox)
        layout.addSpacing(10)
        layout.addLayout(control_buttons_layout)
        layout.addSpacing(20)
        layout.addWidget(QLabel("<b>DANGER ZONE</b>"))
        layout.addLayout(danger_zone_layout)
        layout.addSpacing(20)
        layout.addWidget(self.manage_log_console)
        return tab

    def create_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 20, 30, 20)
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        def add_header(text):
            header = QLabel(text)
            header.setObjectName("header")
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setObjectName("separator")
            vbox = QVBoxLayout()
            vbox.setContentsMargins(0,10,0,5)
            vbox.addWidget(header)
            vbox.addWidget(separator)
            form_layout.addRow(vbox)
        
        add_header("Appearance")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System Default", "Light", "Dark"])
        form_layout.addRow("Theme:", self.theme_combo)

        add_header("Application Behavior")
        self.setting_start_with_windows = QCheckBox("Launch on startup")
        self.setting_start_minimized = QCheckBox("Start minimized in tray")
        form_layout.addRow(self.setting_start_with_windows)
        form_layout.addRow(self.setting_start_minimized)

        add_header("Core Paths")
        self.setting_install_path_edit, install_path_btn = self._create_path_selector("Select Immich Installation Folder", self.settings.get("immich_install_path", ""))
        form_layout.addRow("Immich Installation Path:", self._create_hbox(self.setting_install_path_edit, install_path_btn))
        self.setting_source_dir_edit, source_btn = self._create_path_selector("Select Immich Media Folder", self.settings.get("source_dir", ""))
        form_layout.addRow("Media (Upload) Folder:", self._create_hbox(self.setting_source_dir_edit, source_btn))

        self.save_app_settings_btn = QPushButton("Save Settings")
        self.save_app_settings_btn.clicked.connect(self.collect_and_save_settings)
        
        self._connect_app_setting_signals()
        self.load_app_settings_to_ui()

        layout.addLayout(form_layout)
        layout.addStretch()
        layout.addWidget(self.save_app_settings_btn, 0, Qt.AlignRight)
        
        return tab

    def _create_path_selector(self, title, initial_path):
        edit = QLineEdit(initial_path)
        button = QPushButton("Browse...")
        button.clicked.connect(lambda: self.select_directory(edit, title))
        return edit, button

    def _create_hbox(self, *widgets):
        hbox = QHBoxLayout()
        for widget in widgets:
            hbox.addWidget(widget)
        return hbox

    def _create_progress_log_widgets(self):
        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        log_console = QTextEdit()
        log_console.setReadOnly(True)
        log_console.setVisible(False)
        return progress_bar, log_console
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        current_tab_index = self.tabs.currentIndex()
        if current_tab_index == 1: self.backup_log_console.append(log_entry)
        elif current_tab_index == 2: self.restore_log_console.append(log_entry)
        elif current_tab_index == 3: self.manage_log_console.append(log_entry)
        else: print(log_entry)

    def log_error(self, message):
        self.log(f"ERROR: {message}")
        self.show_error("Operation Failed", message)

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def set_task_running(self, is_running, tab_name=""):
        self.is_task_running = is_running
        
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).lower() != tab_name:
                self.tabs.setTabEnabled(i, not is_running)

        if tab_name == "backup":
            self.backup_full_button.setEnabled(not is_running)
            self.backup_media_button.setEnabled(not is_running)
            self.backup_db_button.setEnabled(not is_running)
            self.backup_progress_bar.setVisible(is_running)
            self.backup_log_console.setVisible(is_running)
            if is_running: self.backup_log_console.clear()
        elif tab_name == "restore":
            is_valid_selection = self.restore_selection_combo.currentIndex() > 0
            self.restore_full_button.setEnabled(not is_running and is_valid_selection)
            self.restore_media_button.setEnabled(not is_running and is_valid_selection)
            self.restore_db_button.setEnabled(not is_running and is_valid_selection)
            self.restore_progress_bar.setVisible(is_running)
            self.restore_log_console.setVisible(is_running)
            if is_running: self.restore_log_console.clear()
        elif tab_name == "manage":
            self.update_manage_tab_state()

    def on_task_finished(self, status):
        active_tab = self.tabs.tabText(self.tabs.currentIndex()).lower()
        self.set_task_running(False, active_tab)
        if status == "success":
            self.tray_icon.showMessage(APP_NAME, "The Immich backup finished successfully.", QSystemTrayIcon.Information, 3000)
            self.refresh_backup_history()
        self.refresh_home_tab()

    def update_progress(self, value, total):
        active_tab_index = self.tabs.currentIndex()
        progress_bar = None
        if active_tab_index == 1: progress_bar = self.backup_progress_bar
        elif active_tab_index == 2: progress_bar = self.restore_progress_bar
        
        if progress_bar:
            progress_bar.setRange(0, total)
            progress_bar.setValue(value)
    
    def select_directory(self, line_edit, title):
        directory = QFileDialog.getExistingDirectory(self, title, line_edit.text())
        if directory: line_edit.setText(directory)

    def start_full_backup(self):
        source_dir = self.settings.get("source_dir")
        backup_dir = self.backup_dir_edit.text()
        if not all([source_dir, backup_dir, Path(source_dir).exists(), Path(backup_dir).exists()]):
            self.show_error("Invalid Paths", "Please select valid source and backup directories in Settings.")
            return
        self.collect_and_save_settings()
        self.set_task_running(True, "backup")
        self.backup_requested.emit(source_dir, backup_dir, self.settings['container_name'], self.settings['db_user'], self.settings['retention_days'])

    def start_media_backup(self):
        source_dir = self.settings.get("source_dir")
        backup_dir = self.backup_dir_edit.text()
        if not all([source_dir, backup_dir, Path(source_dir).exists(), Path(backup_dir).exists()]):
            self.show_error("Invalid Paths", "Please select valid source and backup directories in Settings.")
            return
        self.collect_and_save_settings()
        self.set_task_running(True, "backup")
        self.media_backup_requested.emit(source_dir, backup_dir, self.settings['retention_days'])

    def start_db_backup(self):
        backup_dir = self.backup_dir_edit.text()
        if not backup_dir or not Path(backup_dir).exists():
            self.show_error("Invalid Path", "Please select a valid backup directory.")
            return
        self.collect_and_save_settings()
        self.set_task_running(True, "backup")
        self.db_backup_requested.emit(backup_dir, self.settings['container_name'], self.settings['db_user'], self.settings['retention_days'])

    def select_restore_source_and_refresh(self):
        self.select_directory(self.restore_backup_dir_edit, "Select Backup Folder")
        self.populate_restore_dropdown()

    def populate_restore_dropdown(self):
        self.restore_selection_combo.clear()
        self.restore_selection_combo.addItem("Select a backup...")
        backup_root = self.restore_backup_dir_edit.text()
        if not backup_root or not Path(backup_root).exists():
            return
        
        backups = sorted(
            [d for d in Path(backup_root).glob("ImmichBackup_*") if d.is_dir()],
            key=os.path.getmtime, reverse=True
        )

        for backup_dir in backups:
            try:
                dt_str = backup_dir.name.replace("ImmichBackup_", "")
                dt_obj = datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
                friendly_name = dt_obj.strftime("%Y-%m-%d %I:%M:%S %p")
                self.restore_selection_combo.addItem(friendly_name, userData=str(backup_dir))
            except ValueError:
                continue
    
    def on_restore_selection_changed(self, index):
        is_valid_selection = index > 0 and not self.is_task_running
        self.restore_full_button.setEnabled(is_valid_selection)
        self.restore_media_button.setEnabled(is_valid_selection)
        self.restore_db_button.setEnabled(is_valid_selection)

        if is_valid_selection:
            backup_path = Path(self.restore_selection_combo.currentData())
            media_path = backup_path / "media"
            db_path = backup_path / "database"
            sql_files = list(db_path.glob("*.sql"))

            media_exists = media_path.exists() and any(media_path.iterdir())
            db_exists = db_path.exists() and sql_files

            info_text = f"<b>Backup Location:</b> {backup_path.name}<br>"
            info_text += f"<b>Media Found:</b> {'Yes' if media_exists else 'No'}<br>"
            info_text += f"<b>Database Found:</b> {'Yes' if db_exists else 'No'}"
            self.restore_info_label.setText(info_text)
        else:
            self.restore_info_label.setText("Select a backup to see details.")

    def _get_selected_restore_paths(self):
        backup_path_str = self.restore_selection_combo.currentData()
        if not backup_path_str:
            self.show_error("Error", "No backup selected.")
            return None, None
        
        backup_path = Path(backup_path_str)
        media_path = backup_path / "media"
        sql_files = list((backup_path / "database").glob("*.sql"))

        if not sql_files:
            return media_path, None
        return media_path, str(sql_files[0])

    def start_full_restore(self):
        backup_media_dir, backup_sql_file = self._get_selected_restore_paths()
        target_media_dir = self.settings.get("source_dir")

        if not all([backup_media_dir, backup_sql_file, target_media_dir]):
            self.show_error("Error", "Could not find all necessary files (media, database) for a full restore, or target media directory is not set in settings.")
            return
        
        reply = QMessageBox.warning(self, "Confirm Full Restore",
            "<b>This will completely overwrite your current Immich media and database with the selected backup.</b><br><br>"
            "This action cannot be undone. Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.set_task_running(True, "restore")
            self.full_restore_requested.emit(str(backup_media_dir), target_media_dir, backup_sql_file, self.settings['container_name'], self.settings['db_user'])

    def start_media_restore(self):
        backup_media_dir, _ = self._get_selected_restore_paths()
        target_media_dir = self.settings.get("source_dir")
        if not backup_media_dir or not target_media_dir:
            self.show_error("Error", "Backup media path or target media directory is not valid.")
            return

        reply = QMessageBox.question(self, "Confirm Media Restore", "This will replace the contents of your current media directory. Continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.set_task_running(True, "restore")
            self.media_restore_requested.emit(str(backup_media_dir), target_media_dir)

    def start_db_restore(self):
        _, backup_sql_file = self._get_selected_restore_paths()
        if not backup_sql_file:
            self.show_error("Error", "No SQL file found in the selected backup.")
            return
        
        reply = QMessageBox.question(self, "Confirm Database Restore", "This will overwrite your current Immich database. Continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.set_task_running(True, "restore")
            self.db_restore_requested.emit(backup_sql_file, self.settings['container_name'], self.settings['db_user'])
            
    def update_manage_tab_state(self):
        install_path = self.settings.get("immich_install_path")
        is_installed = install_path and (Path(install_path) / "docker-compose.yml").exists()
        is_running = self.worker._does_container_exist("immich_server")
        
        self.manage_install_update_button.setText("Update" if is_installed else "Install")
        self.safe_update_checkbox.setVisible(is_installed)
        
        is_busy = self.is_task_running
        self.manage_install_update_button.setEnabled(not is_busy)
        
        # This is the user-suggested fix to make startup more robust
        self.manage_start_button.setVisible(bool(is_installed and not is_running))
        self.manage_stop_button.setVisible(bool(is_installed and is_running))

        self.manage_start_button.setEnabled(bool(is_installed and not is_running and not is_busy))
        self.manage_stop_button.setEnabled(bool(is_installed and is_running and not is_busy))
        self.manage_restart_button.setEnabled(bool(is_installed and not is_busy))
        self.open_immich_button.setEnabled(bool(is_installed and is_running and not is_busy))
        self.reinstall_button.setEnabled(bool(is_installed and not is_busy))
        self.uninstall_button.setEnabled(bool(is_installed and not is_busy))
        self.manage_version_combo.setEnabled(bool(not is_busy))
        self.manage_db_pass_edit.setEnabled(bool(not is_busy))


    def populate_versions_combo(self, versions):
        self.manage_version_combo.clear()
        if versions:
            self.latest_version = versions[0]
            for v in versions:
                if v == self.latest_version:
                    self.manage_version_combo.addItem(f"{v} (Latest)")
                else:
                    self.manage_version_combo.addItem(v)
            self.refresh_home_tab()
        else:
            self.manage_version_combo.addItem("Could not fetch versions")

    def update_version_button_text(self, text):
        is_installed = self.settings.get("immich_install_path") and (Path(self.settings.get("immich_install_path")) / "docker-compose.yml").exists()
        if not is_installed:
            self.manage_install_update_button.setText(f"Install {text}")
        else:
            self.manage_install_update_button.setText(f"Update to {text}")

    def open_immich_web(self):
        webbrowser.open("http://localhost:2283")

    def start_install_or_update(self):
        install_path = self.settings.get("immich_install_path")
        is_installed = install_path and (Path(install_path) / "docker-compose.yml").exists()
        
        current_text = self.manage_version_combo.currentText()
        if "Could not" in current_text:
            self.show_error("Error", "Please select a valid version.")
            return
            
        is_latest = "(Latest)" in current_text
        version = current_text.replace(" (Latest)", "").strip()

        if is_installed:
            if self.current_immich_version == "Unknown":
                self.show_error("Update Blocked", "Could not determine the current Immich version.\nPlease ensure Immich is running before attempting an update.")
                return

            reply = QMessageBox.warning(self, "Confirm Update", 
                f"<h3>Update to version '{version}'?</h3>"
                "<p><b>Important:</b> Some updates have breaking changes.</p>"
                "<p>It is <b>strongly recommended</b> that you click 'View Notes' first to check for any special instructions before proceeding.</p>"
                "<hr><p>Do you want to continue with the update?</p>",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.set_task_running(True, "manage")
                self.manage_log_console.clear()
                
                if self.safe_update_checkbox.isChecked():
                    self.safe_update_requested.emit(install_path, self.current_immich_version, version, self.settings['container_name'], self.settings['db_user'], is_latest)
                else:
                    self.update_requested.emit(install_path, version, is_latest)

        else: 
            install_path_to_use = self.settings.get("immich_install_path")
            proceed_with_install = False

            if install_path_to_use and Path(install_path_to_use).exists():
                reply = QMessageBox.question(self, "Confirm Installation Path",
                                             f"An installation path is already set in your settings:\n\n<b>{install_path_to_use}</b>\n\nDo you want to install Immich in this directory?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    proceed_with_install = True
                else:
                    new_path = QFileDialog.getExistingDirectory(self, "Select a Different Folder to Install Immich", str(Path.home()))
                    if new_path:
                        install_path_to_use = new_path
                        proceed_with_install = True
            else:
                install_path_to_use = QFileDialog.getExistingDirectory(self, "Select Folder to Install Immich", str(Path.home()))
                if install_path_to_use:
                    proceed_with_install = True

            if proceed_with_install:
                media_path_to_use = self.settings.get("source_dir")
                proceed_with_media = False
                upload_path = ""

                if media_path_to_use and Path(media_path_to_use).exists():
                    reply = QMessageBox.question(self, "Confirm Media Path",
                                                 f"A media path is already set in your settings:\n\n<b>{media_path_to_use}</b>\n\nDo you want to use this for your media uploads?",
                                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if reply == QMessageBox.Yes:
                        upload_path = media_path_to_use
                        proceed_with_media = True
                    else:
                        new_media_path = QFileDialog.getExistingDirectory(self, "Select a Different Folder for Media (Uploads)", str(Path.home()))
                        if new_media_path:
                            upload_path = new_media_path
                            proceed_with_media = True
                else:
                    upload_path = QFileDialog.getExistingDirectory(self, "Select Folder for Media (Uploads)", install_path_to_use)
                    if upload_path:
                        proceed_with_media = True

                if proceed_with_media:
                    self.setting_install_path_edit.setText(install_path_to_use)
                    self.setting_source_dir_edit.setText(upload_path)
                    self.collect_and_save_settings()

                    db_pass = self.manage_db_pass_edit.text() or "postgres"
                    self.set_task_running(True, "manage")
                    self.manage_log_console.clear()
                    self.install_requested.emit(install_path_to_use, version, db_pass, upload_path, is_latest)

    def request_release_notes(self):
        current_text = self.manage_version_combo.currentText()
        if not current_text or "Could not" in current_text:
            self.show_error("Error", "Please select a valid version first.")
            return
        version = current_text.replace(" (Latest)", "").strip()
        self.view_release_notes_btn.setText("Fetching...")
        self.release_notes_requested.emit(version)

    def display_release_notes(self, version, notes):
        self.view_release_notes_btn.setText("View Notes")
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Release Notes for {version}")
        dialog.setMinimumSize(700, 550)
        
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(notes)
        layout.addWidget(text_edit)
        
        button_box = QHBoxLayout()
        button_box.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_box.addWidget(close_button)
        layout.addLayout(button_box)
        
        dialog.exec()

    def start_manage_action(self, action):
        install_path = self.settings.get("immich_install_path")
        self.set_task_running(True, "manage")
        self.manage_log_console.clear()
        self.action_requested.emit(install_path, action)

    def start_reinstall(self):
        install_path = self.settings.get("immich_install_path")
        reply = QMessageBox.warning(self, "Confirm Re-install",
            "<b>This will PERMANENTLY DELETE your Immich database and settings.</b><br>"
            "Your media files (photos/videos) will NOT be deleted.<br><br>"
            "This is useful for starting from a clean slate. This action cannot be undone.<br>"
            "Are you sure you want to proceed?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.set_task_running(True, "manage")
            self.manage_log_console.clear()
            self.reinstall_requested.emit(install_path)

    def start_uninstall(self):
        install_path = self.settings.get("immich_install_path")
        if not install_path or not Path(install_path).exists():
            self.show_error("Error", "Immich installation path is not set or does not exist.\n\nPlease set it in the Settings tab.")
            return

        reply = QMessageBox.question(self, "Confirm Uninstall",
                                     "<h3>This will permanently remove the Immich application.</h3>"
                                     "<p>The following will be deleted:</p>"
                                     "<ul>"
                                     "<li>Immich Docker containers</li>"
                                     "<li>The Immich database (all user and photo metadata)</li>"
                                     "<li>Application configuration files (.yml, .env)</li>"
                                     "</ul>"
                                     "<p><b>Your media library (the actual photo and video files) WILL NOT be deleted.</b></p>"
                                     "<hr>"
                                     "<p>Are you sure you want to proceed?</p>",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.set_task_running(True, "manage")
            self.manage_log_console.clear()
            self.log("Starting full uninstall (media files will be kept)...")
            self.uninstall_requested.emit(install_path)

    def load_app_settings_to_ui(self):
        self._disconnect_app_setting_signals()
        self.setting_start_with_windows.setChecked(self.settings.get("start_with_windows", False))
        self.setting_start_minimized.setChecked(self.settings.get("start_minimized", False))
        self.setting_install_path_edit.setText(self.settings.get("immich_install_path", ""))
        self.setting_source_dir_edit.setText(self.settings.get("source_dir", ""))
        self.theme_combo.setCurrentIndex({"system": 0, "light": 1, "dark": 2}.get(self.settings.get('theme', 'system'), 0))
        self._update_save_button_state("app", False)
        self._connect_app_setting_signals()

    def load_backup_settings_to_ui(self):
        self._disconnect_backup_setting_signals()
        self.backup_dir_edit.setText(self.settings.get("backup_dir", ""))
        self.setting_retention_days.setValue(self.settings.get("retention_days", 7))
        self.setting_container_name.setText(self.settings.get("container_name", "immich_postgres"))
        self.setting_db_user.setText(self.settings.get("db_user", "postgres"))
        self.schedule_enabled_check.setChecked(self.settings.get("schedule_enabled", False))
        self.schedule_time_edit.setTime(QTime.fromString(self.settings.get("schedule_time", "02:00"), "HH:mm"))
        self.schedule_freq_combo.setCurrentText(self.settings.get("schedule_frequency", "Daily"))
        self.schedule_type_combo.setCurrentText(self.settings.get("schedule_backup_type", "Full Backup"))
        self.schedule_day_combo.setCurrentText(self.settings.get("schedule_day", "Monday"))
        self.schedule_dom_spin.setValue(self.settings.get("schedule_day_of_month", 1))

        self._update_save_button_state("backup", False)
        self._connect_backup_setting_signals()

    def collect_and_save_settings(self):
        self.settings['theme'] = ["system", "light", "dark"][self.theme_combo.currentIndex()]
        self.settings['start_with_windows'] = self.setting_start_with_windows.isChecked()
        self.settings['start_minimized'] = self.setting_start_minimized.isChecked()
        self.settings['immich_install_path'] = self.setting_install_path_edit.text()
        self.settings['source_dir'] = self.setting_source_dir_edit.text()
        
        self.settings['retention_days'] = self.setting_retention_days.value()
        self.settings['container_name'] = self.setting_container_name.text()
        self.settings['db_user'] = self.setting_db_user.text()
        self.settings["schedule_enabled"] = self.schedule_enabled_check.isChecked()
        self.settings["schedule_time"] = self.schedule_time_edit.time().toString("HH:mm")
        self.settings["schedule_frequency"] = self.schedule_freq_combo.currentText()
        self.settings["schedule_backup_type"] = self.schedule_type_combo.currentText()
        self.settings["schedule_day"] = self.schedule_day_combo.currentText()
        self.settings["schedule_day_of_month"] = self.schedule_dom_spin.value()
        self.settings['backup_dir'] = self.backup_dir_edit.text()
        
        self.save_settings()

        self.backup_settings_dirty = False
        self.app_settings_dirty = False
        
        clicked_button = self.sender()
        if clicked_button == self.save_backup_settings_btn:
            self.save_backup_settings_btn.setText("✓ Saved")
            QTimer.singleShot(2000, lambda: self._update_save_button_state("backup", False))
        elif clicked_button == self.save_app_settings_btn:
            self.save_app_settings_btn.setText("✓ Saved")
            QTimer.singleShot(2000, lambda: self._update_save_button_state("app", False))
        else:
            self._update_save_button_state("backup", False)
            self._update_save_button_state("app", False)
        
        self.manage_install_path_label.setText(self.settings['immich_install_path'] or "Not Set")
        self.apply_theme()
        self.set_startup(self.settings['start_with_windows'])
    
    def _connect_backup_setting_signals(self):
        self.backup_dir_edit.textChanged.connect(self.mark_backup_settings_dirty)
        self.setting_retention_days.valueChanged.connect(self.mark_backup_settings_dirty)
        self.setting_container_name.textChanged.connect(self.mark_backup_settings_dirty)
        self.setting_db_user.textChanged.connect(self.mark_backup_settings_dirty)
        self.schedule_enabled_check.toggled.connect(self.mark_backup_settings_dirty)
        self.schedule_time_edit.timeChanged.connect(self.mark_backup_settings_dirty)
        self.schedule_freq_combo.currentIndexChanged.connect(self.mark_backup_settings_dirty)
        self.schedule_type_combo.currentIndexChanged.connect(self.mark_backup_settings_dirty)
        self.schedule_day_combo.currentIndexChanged.connect(self.mark_backup_settings_dirty)
        self.schedule_dom_spin.valueChanged.connect(self.mark_backup_settings_dirty)

    def _disconnect_backup_setting_signals(self):
        try: self.backup_dir_edit.textChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_retention_days.valueChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_container_name.textChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_db_user.textChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_enabled_check.toggled.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_time_edit.timeChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_freq_combo.currentIndexChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_type_combo.currentIndexChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_day_combo.currentIndexChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.schedule_dom_spin.valueChanged.disconnect(self.mark_backup_settings_dirty)
        except (TypeError, RuntimeError): pass

    def _connect_app_setting_signals(self):
        self.theme_combo.currentIndexChanged.connect(self.mark_app_settings_dirty)
        self.setting_start_with_windows.toggled.connect(self.mark_app_settings_dirty)
        self.setting_start_minimized.toggled.connect(self.mark_app_settings_dirty)
        self.setting_install_path_edit.textChanged.connect(self.mark_app_settings_dirty)
        self.setting_source_dir_edit.textChanged.connect(self.mark_app_settings_dirty)
        
    def _disconnect_app_setting_signals(self):
        try: self.theme_combo.currentIndexChanged.disconnect(self.mark_app_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_start_with_windows.toggled.disconnect(self.mark_app_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_start_minimized.toggled.disconnect(self.mark_app_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_install_path_edit.textChanged.disconnect(self.mark_app_settings_dirty)
        except (TypeError, RuntimeError): pass
        try: self.setting_source_dir_edit.textChanged.disconnect(self.mark_app_settings_dirty)
        except (TypeError, RuntimeError): pass

    def mark_backup_settings_dirty(self):
        self.backup_settings_dirty = True
        self._update_save_button_state("backup", True)

    def mark_app_settings_dirty(self):
        self.app_settings_dirty = True
        self._update_save_button_state("app", True)

    def _update_save_button_state(self, tab_name, dirty):
        button = self.save_backup_settings_btn if tab_name == "backup" else self.save_app_settings_btn
        original_text = "Save Backup Settings" if tab_name == "backup" else "Save Settings"
        
        button.setEnabled(dirty)
        button.setText("Save Changes*" if dirty else original_text)
        button.setObjectName("save_needed_button" if dirty else "")
        button.style().polish(button)

    def prompt_to_save_changes(self, settings_type):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unsaved Changes")
        msg_box.setText(f"You have unsaved changes in the {settings_type} settings.")
        msg_box.setInformativeText("Do you want to save them before switching tabs?")
        msg_box.setIcon(QMessageBox.Question)
        save_button = msg_box.addButton("Save", QMessageBox.AcceptRole)
        discard_button = msg_box.addButton("Discard", QMessageBox.DestructiveRole)
        cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == save_button:
            self.collect_and_save_settings()
            return True
        elif clicked == discard_button:
            if settings_type == "Backup": self.load_backup_settings_to_ui()
            else: self.load_app_settings_to_ui()
            return True
        return False

    def toggle_schedule_controls(self, checked):
        for widget in [self.schedule_time_edit, self.schedule_freq_combo, self.schedule_type_combo, self.schedule_day_combo, self.schedule_dom_spin, self.schedule_day_label, self.schedule_dom_label]:
            widget.setEnabled(checked)
        if checked: self.update_schedule_day_visibility(self.schedule_freq_combo.currentText())

    def update_schedule_day_visibility(self, frequency):
        is_weekly = (frequency == "Weekly")
        is_monthly = (frequency == "Monthly")
        self.schedule_day_label.setVisible(is_weekly)
        self.schedule_day_combo.setVisible(is_weekly)
        self.schedule_dom_label.setVisible(is_monthly)
        self.schedule_dom_spin.setVisible(is_monthly)

    def check_for_scheduled_backup(self):
        if self.is_task_running or not self.settings.get("schedule_enabled"):
            return

        now = datetime.now()
        last_run_ts = self.settings.get("last_auto_backup_ts", 0)
        last_run_dt = datetime.fromtimestamp(last_run_ts)

        # Stop if a backup has already run today.
        if last_run_dt.date() == now.date():
            return

        schedule_time = QTime.fromString(self.settings.get("schedule_time", "02:00"), "HH:mm")

        # Stop if it's not yet time for the backup.
        if now.time() < schedule_time:
            return

        freq = self.settings.get("schedule_frequency")
        run_today = (freq == "Daily") or \
                    (freq == "Weekly" and now.strftime("%A") == self.settings.get("schedule_day")) or \
                    (freq == "Monthly" and now.day == self.settings.get("schedule_day_of_month"))

        if run_today:
            backup_type = self.settings.get("schedule_backup_type", "Full Backup")
            self.log(f"SCHEDULER: Triggering automated '{backup_type}' backup.")
            self.tray_icon.showMessage(APP_NAME, f"Starting scheduled '{backup_type}' backup.", QSystemTrayIcon.Information, 3000)
            self.tabs.setCurrentIndex(1) # Switch to backup tab to show progress
            
            if backup_type == "Media Only": self.start_media_backup()
            elif backup_type == "Database Only": self.start_db_backup()
            else: self.start_full_backup()

            self.settings["last_auto_backup_ts"] = now.timestamp()
            self.save_settings()

    def refresh_home_tab(self):
        self.docker_status_requested.emit(self.settings.get("immich_install_path", ""))

    def update_home_dashboard(self, payload):
        self.current_immich_version = payload.get("version", "Unknown")
        status_dict = payload.get("containers", {})

        if self.latest_version and self.current_immich_version != "Unknown":
            self.version_status_label.setVisible(True)
            if self.latest_version == self.current_immich_version:
                self.version_status_label.setText(f"✓ You are running the latest version of Immich ({self.current_immich_version})")
                self.version_status_label.setObjectName("version_ok")
            else:
                self.version_status_label.setText(f"ℹ A new version is available ({self.latest_version}). Go to the Manage tab to update.")
                self.version_status_label.setObjectName("version_update")
        else:
             self.version_status_label.setText(f"Current Version: {self.current_immich_version}")
             self.version_status_label.setVisible(True)
             self.version_status_label.setObjectName("")
        self.version_status_label.style().polish(self.version_status_label)

        for name, label in self.container_status_labels.items():
            status = status_dict.get(name, 'unknown')
            label.setText(status.upper())
            color = {"running": "#27ae60", "exited": "#f39c12", "stopped": "#f39c12"}.get(status, "#e74c3c")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            
        self.update_manage_tab_state()

        if self.is_initial_load:
            self.is_initial_load = False
            self.ready_to_show.emit()

    def get_next_schedule_datetime(self):
        if not self.settings.get("schedule_enabled"):
            return None

        now = datetime.now()
        schedule_time = QTime.fromString(self.settings.get("schedule_time", "02:00"), "HH:mm")
        
        today_schedule = now.replace(hour=schedule_time.hour(), minute=schedule_time.minute(), second=0, microsecond=0)

        next_run = None
        freq = self.settings.get("schedule_frequency")

        if freq == "Daily":
            next_run = today_schedule if now < today_schedule else today_schedule + timedelta(days=1)
        
        elif freq == "Weekly":
            days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            target_day_index = days_of_week.index(self.settings.get("schedule_day", "Monday"))
            days_ahead = (target_day_index - now.weekday() + 7) % 7
            
            if days_ahead == 0 and now > today_schedule:
                days_ahead = 7
            
            next_run = today_schedule + timedelta(days=days_ahead)

        elif freq == "Monthly":
            target_day = self.settings.get("schedule_day_of_month", 1)
            try:
                next_run = today_schedule.replace(day=target_day)
                if now > next_run:
                    # Move to next month
                    next_month = (now.month % 12) + 1
                    next_year = now.year + (1 if now.month == 12 else 0)
                    next_run = next_run.replace(year=next_year, month=next_month)
            except ValueError: # Handle days not present in a month (e.g. 31st)
                next_run = None # Simplification: don't show countdown for invalid day

        return next_run

    def update_countdown(self):
        if not self.settings.get("schedule_enabled"):
            self.countdown_label.setText("Scheduler is disabled.")
            return

        next_run_dt = self.get_next_schedule_datetime()
        if not next_run_dt:
            self.countdown_label.setText("Invalid schedule date.")
            return

        delta = next_run_dt - datetime.now()
        
        if delta.total_seconds() <= 0:
            self.countdown_label.setText("Scheduled time has passed for today.")
            return

        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        if days > 0:
            self.countdown_label.setText(f"{days}d {hours}h {minutes}m {seconds}s")
        else:
            self.countdown_label.setText(f"{hours}h {minutes}m {seconds}s")


    def refresh_backup_history(self):
        self.history_list.clear()
        backup_dir = self.settings.get("backup_dir", "")
        if not backup_dir: return
        log_file = Path(backup_dir) / "backup_log.json"
        if log_file.exists():
            try:
                with open(log_file, 'r') as f: history = json.load(f)
                for item in history:
                    dt = datetime.fromisoformat(item['timestamp']).strftime("%Y-%m-%d %I:%M %p")
                    status = item['status'].capitalize()
                    icon = "✔" if status == 'Success' else "✖"
                    duration = f"{item['duration_seconds']}s"
                    backup_type = item.get("type", "Full")
                    
                    list_item_text = f"{icon} {dt} - {status} ({backup_type} | {duration})"
                    if item.get("error"): list_item_text += f"\n   Error: {item['error']}"

                    list_item = QListWidgetItem(list_item_text)
                    if status != 'Success': list_item.setForeground(QColor("#fa383e"))
                    self.history_list.addItem(list_item)
            except Exception as e:
                self.history_list.addItem(f"Error reading backup log: {e}")

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_and_raise)
        menu.addAction(show_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason):
        # Show window on left-click
        if reason == QSystemTrayIcon.Trigger:
            self.show_and_raise()

    def show_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        QApplication.instance().quit()

    def set_startup(self, enable):
        if not IS_WINDOWS:
            self.log("Startup configuration is only supported on Windows.")
            return
        try:
            key_path = REG_KEY_PATH
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            if enable:
                command = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
                self.log("Set to run on startup.")
            else:
                winreg.DeleteValue(key, APP_NAME)
                self.log("Removed from startup.")
            winreg.CloseKey(key)
        except FileNotFoundError:
             if not enable:
                 self.log("Not set to run on startup (key not found).")
             else:
                 self.log_error("Could not create startup registry key.")
        except Exception as e:
            self.log_error(f"Error setting startup: {e}")

    def closeEvent(self, event):
        if self.is_task_running:
            reply = QMessageBox.question(self, 'Task in Progress', "A task is running. Are you sure you want to quit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        
        # On close, hide to system tray instead of quitting
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            APP_NAME,
            "Application is still running in the background.",
            QSystemTrayIcon.Information,
            2000
        )

