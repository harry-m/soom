import os
from flask import Flask, render_template, request

from flask_httpauth import HTTPBasicAuth

from flask.cli import with_appcontext

import click

import tasks
from app_utils import *
from celery_config import celery
from database import TaskCache, database as db
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.debug = True
app.secret_key = os.getenv('FLASK_SECRET_KEY', "sep897rugb04w57bg40957gb9pergbouerdbv.lxcnv,kdjfbgoeri6yutbgodznyujxikcisgrfbgdsvabolisj")
auth = HTTPBasicAuth()

# Configure database connection
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database with the app

db.init_app(app)

# Simulated user database
users = {
    "admin": os.getenv('ADMIN_PASSWORD'),
}

@auth.verify_password
def verify_password(username, password):
    # Verify username and password
    if username in users and users[username] == password:
        return username  # Authenticated user
    
    return None  # Authentication failed


@app.route('/')
@auth.login_required
def main():
    available_tasks = []

    for task in celery.tasks.keys():
        if not task.startswith('task'):
            continue

        task_name = task.split('.')[-1]
        task_handler = getattr(getattr(tasks, task_name), task_name)

        available_tasks.append({
            "name": task_name,
            "title": task_name.replace('_', ' ').title(),
            "handler": task_handler,
            "template": getattr(getattr(tasks, task_name), f"{task_name}_template"),
            "url_path": url_for('run_task', name=task_name, _external=True),
            "url_params": format_apicall_url_params(task_handler)
        })

    return render_template('main.html', available_tasks=available_tasks)


@app.route('/task/<name>', methods=['POST'])
@auth.login_required
def run_task(name):
    # Get a format if one was specified, or default to plain
    format = request.form.get('format').lower() if request.form.get('format') else "plain"

    if format not in ['plain', 'html', 'json']:
        return send_message("Invalid format", format, "error")
    

    # Get an action if one was specified, or default to run
    action = request.form.get('action').lower() if request.form.get('action') else "run"

    if action not in ['run', 'enqueue']:
        return send_message("Invalid or missing action", format, "error")
    

    # Check if the function exists in the tasks module
    if not hasattr(tasks, name):
        return send_message(f"Task not found", format, "error")

    task_function = getattr(getattr(tasks, name), name)


    # Ensure it's actually a callable function
    if not callable(task_function):
        return send_message(f"'{name}' is not callable", format, "error")


    # Extract form parameters
    params = request.form.to_dict()
    params.pop('action', None)
    params.pop('format', None)


    # Enqueue or run the task, as directed
    try:
        if action == "enqueue":
            queued_task = celery.send_task(f"tasks.{name}.{name}", kwargs=params)

            return send_message(f"Your task {queued_task.id} has been enqueued", format, "info")
        
        else:
            # Call the function with form parameters
            task_result = task_function(**params)
            
            return send_result(task_result, format, 'result.html')
    
    # Handle exceptions
    except TypeError as e:
        return send_message(f"Invalid parameters: {str(e)}", format, "error")
    
    except Exception as e:
        return send_message(f"run_task failed: {e}", format, "error")

@click.command("celery-worker")
@with_appcontext
def celery_worker():
    celery.worker_main(["worker", "--loglevel=info", "-B", "--concurrency=4"])

app.cli.add_command(celery_worker)

@click.command("init-db")
@with_appcontext
def init_db():
    db.create_all()

app.cli.add_command(init_db)

