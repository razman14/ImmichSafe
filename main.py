import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
from config import APP_NAME, IS_WINDOWS

# On Windows, setting an explicit AppUserModelID is necessary to ensure that the
# taskbar icon and notifications are associated with the application itself,
# rather than with the Python interpreter. This prevents the title from showing up as "python.exe".
if IS_WINDOWS:
    import ctypes
    app_id = f'ImmichSafe'  # A unique ID for the application
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Setting the application name is also good practice.
    app.setApplicationName(APP_NAME)

    window = MainWindow()

    def show_window():
        if window.settings.get("start_minimized", False):
            window.hide()
            # The notification for starting minimized is now handled inside MainWindow
            # to ensure consistency with other notifications.
        else:
            window.show()

    # Defer showing the window until the initial data load is complete.
    window.ready_to_show.connect(show_window)

    sys.exit(app.exec())