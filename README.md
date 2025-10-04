# ImmichSafe

### The Ultimate Desktop Companion for Your Immich Server

# 

**ImmichSafe** is a user-friendly, cross-platform desktop application for Windows, macOS, and Linux, designed to simplify the management, backup, and restoration of your self-hosted [Immich](https://immich.app/ "null") photo and video management server. It provides a graphical user interface for complex Docker commands, making Immich administration accessible to everyone.

> **Note:** ImmichSafe is an independent, third-party tool created by the community. It is not officially affiliated with, endorsed by, or supported by the official Immich project.

## Table of Contents

# 

-   [Key Features](https://www.google.com/search?q=%23key-features "null")
    
-   [Screenshots](https://www.google.com/search?q=%23screenshots "null")
    
-   [Requirements](https://www.google.com/search?q=%23requirements "null")
    
-   [Installation and Usage](https://www.google.com/search?q=%23installation-and-usage "null")
    
-   [Quick Start Guide](https://www.google.com/search?q=%23quick-start-guide "null")
    
-   [Contributing](https://www.google.com/search?q=%23contributing "null")
    
-   [License](https://www.google.com/search?q=%23license "null")
    

## Key Features

# 

-   **Cross-Platform**: Works natively on Windows, macOS, and Linux.

-   **Remote Management**: Securely manage a remote Immich server over SSH. All core functions—install, update, backup, restore, and status monitoring—can be executed on a remote machine.
    
-   **Full Immich Lifecycle Management**: Install, update, start, stop, restart, and uninstall your Immich server with simple button clicks.
    
-   **One-Click Backups**: Perform full backups of your entire Immich instance, or backup just your media library or database individually.
    
-   **Automated Backups**: Schedule automatic backups to run daily, weekly, or monthly at a time of your choosing. A live countdown on the home page shows you when the next backup is planned.
    
-   **Safe Updates**: Update your Immich instance with confidence. The "Safe Update" feature automatically backs up your database before updating and can roll back to the previous version if the update fails.
    
-   **Simple Restoration**: Restore your media, database, or a full instance from a previous backup with a few clicks.
    
-   **Live Status Dashboard**: See the real-time status of all your Immich Docker containers (server, microservices, machine learning, etc.) at a glance.
    
-   **System Tray Integration**: The application runs conveniently in the system tray, minimizing to the background and providing notifications for key events.
    

## Screenshots

# 

**Home Tab:** Monitor the real-time status of your Immich containers and see the countdown to your next scheduled backup.

![Home Tab](https://github.com/epichfallen/ImmichSafe/blob/main/assets/screenshots/home-tab.png)

**Backup Tab:** Easily configure backup schedules, run manual backups, and view your recent backup history.

![Backup Tab](https://github.com/epichfallen/ImmichSafe/blob/main/assets/screenshots/backup-tab.png)

**Restore Tab:** Select from a list of previous backups to restore your media, database, or a full instance.

![Restore Tab](https://github.com/epichfallen/ImmichSafe/blob/main/assets/screenshots/restore-tab.png)

**Manage Tab:** Install, update, and control your Immich server with simple actions.

![Manage Tab](https://github.com/epichfallen/ImmichSafe/blob/main/assets/screenshots/manage-tab.png)

**Settings Tab:** Configure all core application paths, SSH connections, and behaviors in one place.

![Settings Tab](https://github.com/epichfallen/ImmichSafe/blob/main/assets/screenshots/settings-tab.png)

## Requirements

# 

Before you begin, ensure you have the following installed on your machine:

1.  **Operating System**: Windows 10+, macOS 10.15+, or a modern Linux distribution (e.g., Ubuntu, Fedora).
    
2.  **Docker Desktop / Docker Engine**: The application interacts directly with Docker to manage the Immich containers.
    
    -   [Download Docker Desktop here](https://www.docker.com/products/docker-desktop/ "null").
        
3.  **Python**: Python 3.8 or newer.
    

## Installation and Usage

# 

Follow these steps to get ImmichSafe running from the source code:

### 1\. Clone the Repository

# 

Clone this repository to your local machine:

    git clone [https://github.com/epichfallen/ImmichSafe.git](https://github.com/epichfallen/ImmichSafe.git)
    cd ImmichSafe

### 2\. Install Dependencies

# 

Install the required Python packages using the `requirements.txt` file. It is highly recommended to do this within a virtual environment.

    # Create and activate a virtual environment (optional but recommended)
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `.\venv\Scripts\activate`
    
    # Install requirements
    pip install -r requirements.txt
    

### 3\. Run the Application

# 

Execute the `main.py` script to launch the application.

    python3 main.py
    

## Quick Start Guide

### 1\. Initial Setup (Settings Tab)

# 

-   Navigate to the **Settings** tab.
    
-   **For a Local Server:**
    
    -   Set your **Immich Installation Path**. This is the folder on your local machine where the `docker-compose.yml` file will be stored (e.g., `C:\Immich` or `~/immich`).
        
    -   Set your **Media (Upload) Folder**. This is the parent directory on your local machine for photos and videos (e.g., `Y:\MyPhotos` or `~/Pictures/ImmichLibrary`).
        
-   **For a Remote Server:**
    
    -   Check **"Enable Remote Management"**.
        
    -   Enter your server's IP, port, username, and password/SSH key.
        
    -   The **Immich Installation Path** and **Media (Upload) Folder** must be the full paths _on the remote server_ (e.g., `/home/user/immich` or `/mnt/data/photos`).
        
-   Click **"Save Settings"**.
    

### 2\. Install Immich (Manage Tab)

# 

-   Go to the **Manage** tab.
    
-   Select the version of Immich you wish to install from the dropdown menu.
    
-   Click the **"Install"** button. The application will install Immich either locally or remotely based on your settings.
    

### 3\. Configure Backups (Backup Tab)

# 

-   Go to the **Backup** tab.
    
-   Select a **Backup Folder**. This path should be on your local machine for local backups, or a path on the remote server for remote backups.
    
-   To enable scheduled backups, check **"Enable automatic backups"** and configure your desired frequency and time.
    
-   Click **"Save Backup Settings"**.

## Contributing

# 

Contributions are welcome! If you have suggestions for improvements or find a bug, please feel free to open an issue or submit a pull request.

## License

# 

This project is licensed under the MIT License. See the `LICENSE` file for details.

