# Peso app

A lightweight, local web application built with Python and Flask to help track savings goals, budgets, and daily expenses. 

## Prerequisites
Before you begin, ensure you have [Python](https://www.python.org/downloads/) installed on your computer.

## Installation & Setup

**1. Clone the repository**
Download the code to your local machine:
```bash
git clone https://github.com/PotetoFry/peso-flask.git
cd peso-flask
```
2. Create a Virtual Environment
It's highly recommended to run this app inside a virtual environment to keep dependencies cleanly separated.

```bash
python -m venv venv
```
3. Activate the Virtual Environment

Windows:

``` bash
venv\Scripts\activate
Mac/Linux:
```
```bash
source venv/bin/activate
```
4. Install Dependencies
Install all required Python packages (like Flask and SQLAlchemy) from the recipe list:

```bash
pip install -r requirements.txt
```
Running the Application
For Windows Users:
Simply double-click the start_server.bat file located in the main project folder. This will automatically activate the virtual environment, boot up the local server, and open a terminal window for your logs.

Manual Start (Mac/Linux/Windows Terminal):
Make sure your virtual environment is active, then run:

bash
```
python app.py
```
Once the server is running, open your web browser and navigate to:

👉 http://127.0.0.1:5000
