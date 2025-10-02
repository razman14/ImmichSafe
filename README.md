ImmichSafe - The Ultimate Companion for Your Immich Server
ImmichSafe is a user-friendly desktop application for Windows designed to simplify the management, backup, and restoration of your self-hosted Immich photo and video management server. It provides a graphical user interface for complex Docker commands, making Immich administration accessible to everyone.

(Suggestion: Replace this link with a screenshot of your application's home tab)

Key Features
Full Immich Lifecycle Management: Install, update, start, stop, restart, and uninstall your Immich server with simple button clicks.

One-Click Backups: Perform full backups of your entire Immich instance, or backup just your media library or database individually.

Automated Backups: Schedule automatic backups to run daily, weekly, or monthly at a time of your choosing. A live countdown on the home page shows you when the next backup is planned.

Safe Updates: Update your Immich instance with confidence. The "Safe Update" feature automatically backs up your database before updating and can roll back to the previous version if the update fails.

Simple Restoration: Restore your media, database, or a full instance from a previous backup with a few clicks.

Live Status Dashboard: See the real-time status of all your Immich Docker containers (server, microservices, machine learning, etc.) at a glance.

System Tray Integration: The application runs conveniently in the system tray, minimizing to the background and providing notifications for key events like completed backups.

Requirements
Before you begin, ensure you have the following installed and running on your Windows machine:

Windows Operating System: Windows 10 or newer.

Docker Desktop: The application interacts directly with Docker to manage the Immich containers. Download and install Docker Desktop here.

Python: Python 3.8 or newer.

Installation and Usage
Follow these steps to get ImmichSafe running from the source code:

Clone the Repository:

git clone [https://github.com/your-username/ImmichSafe.git](https://github.com/your-username/ImmichSafe.git)
cd ImmichSafe

Install Dependencies:
Install the required Python packages using the requirements.txt file.

pip install -r requirements.txt

Run the Application:
Execute the main.py script to launch the application.

python main.py

Quick Start Guide
Initial Setup (Settings Tab):

Go to the Settings tab.

Set your Immich Installation Path. This is the folder where the docker-compose.yml file will be stored (e.g., C:\Immich).

Set your Media (Upload) Folder. This is the parent directory where all your photos and videos will be stored (e.g., Y:\MyPhotos). The application will automatically create the necessary subfolders (upload, library, etc.) inside this directory.

Install Immich (Manage Tab):

Go to the Manage tab.

Select the version of Immich you wish to install from the dropdown menu.

Click the "Install" button and follow the prompts. The application will download the necessary files and start your Immich server.

Configure Backups (Backup Tab):

Go to the Backup tab.

Select a Backup Folder where you want to store your backups.

To enable scheduled backups, check "Enable automatic backups" and configure your desired frequency and time.

Click "Save Backup Settings".

Run a Manual Backup:

On the Backup tab, click "Backup All" to perform your first full backup. You can monitor the progress in the log window at the bottom.

Contributing
Contributions are welcome! If you have suggestions for improvements or find a bug, please feel free to open an issue or submit a pull request.

License
This project is licensed under the MIT License. See the LICENSE file for details.
