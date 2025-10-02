ImmichSafe
==========

### The Ultimate Desktop Companion for Your Immich Server

**ImmichSafe** is a user-friendly desktop application for Windows designed to simplify the management, backup, and restoration of your self-hosted [Immich](https://immich.app/ "null") photo and video management server. It provides a graphical user interface for complex Docker commands, making Immich administration accessible to everyone.

Disclaimer
----------

> **Note:** ImmichSafe is an independent, third-party tool created by the community. It is not officially affiliated with, endorsed by, or supported by the official Immich project.

Table of Contents
-----------------

-   [Key Features](https://www.google.com/search?q=%23key-features "null")

-   [Requirements](https://www.google.com/search?q=%23requirements "null")

-   [Installation and Usage](https://www.google.com/search?q=%23installation-and-usage "null")

-   [Quick Start Guide](https://www.google.com/search?q=%23quick-start-guide "null")

-   [Contributing](https://www.google.com/search?q=%23contributing "null")

-   [License](https://www.google.com/search?q=%23license "null")

Key Features
------------

-   **Full Immich Lifecycle Management**: Install, update, start, stop, restart, and uninstall your Immich server with simple button clicks.

-   **One-Click Backups**: Perform full backups of your entire Immich instance, or backup just your media library or database individually.

-   **Automated Backups**: Schedule automatic backups to run daily, weekly, or monthly at a time of your choosing. A live countdown on the home page shows you when the next backup is planned.

-   **Safe Updates**: Update your Immich instance with confidence. The "Safe Update" feature automatically backs up your database before updating and can roll back to the previous version if the update fails.

-   **Simple Restoration**: Restore your media, database, or a full instance from a previous backup with a few clicks.

-   **Live Status Dashboard**: See the real-time status of all your Immich Docker containers (server, microservices, machine learning, etc.) at a glance.

-   **System Tray Integration**: The application runs conveniently in the system tray, minimizing to the background and providing notifications for key events.

Requirements
------------

Before you begin, ensure you have the following installed and running on your Windows machine:

1.  **Windows Operating System**: Windows 10 or newer.

2.  **Docker Desktop**: The application interacts directly with Docker to manage the Immich containers. [Download and install Docker Desktop here](https://www.docker.com/products/docker-desktop/ "null").

3.  **Python**: Python 3.8 or newer.

Installation and Usage
----------------------

Follow these steps to get ImmichSafe running from the source code:

### 1\. Clone the Repository

Clone this repository to your local machine:

```
git clone [https://github.com/epichfallen/ImmichSafe.git](https://github.com/epichfallen/ImmichSafe.git)
cd ImmichSafe

```



### 2\. Install Dependencies

Install the required Python packages using the `requirements.txt` file. It is highly recommended to do this within a virtual environment.

```
# Optional: Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

```

### 3\. Run the Application

Execute the `main.py` script to launch the application.

```
python main.py

```

Quick Start Guide
-----------------

1.  **Initial Setup (Settings Tab)**

    -   Navigate to the **Settings** tab.

    -   Set your **Immich Installation Path**. This is the folder where the `docker-compose.yml` file will be stored (e.g., `C:\Immich`).

    -   Set your **Media (Upload) Folder**. This is the parent directory where all your photos and videos will be stored (e.g., `Y:\MyPhotos`). The application will automatically create the necessary subfolders (`upload`, `library`, etc.) inside this directory.

2.  **Install Immich (Manage Tab)**

    -   Go to the **Manage** tab.

    -   Select the version of Immich you wish to install from the dropdown menu.

    -   Click the **"Install"** button and follow the prompts.

3.  **Configure Backups (Backup Tab)**

    -   Go to the **Backup** tab.

    -   Select a **Backup Folder** where you want to store your backups.

    -   To enable scheduled backups, check **"Enable automatic backups"** and configure your desired frequency and time.

    -   Click **"Save Backup Settings"**.

4.  **Run a Manual Backup**

    -   On the **Backup** tab, click **"Backup All"** to perform your first full backup. You can monitor the progress in the log window.

Contributing
------------

Contributions are welcome! If you have suggestions for improvements or find a bug, please feel free to open an issue or submit a pull request.

License
-------

This project is licensed under the MIT License. See the `LICENSE` file for details.
