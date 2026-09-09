# -*- coding: utf-8 -*-

import os

import flask_migrate
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()

migrations_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "migrations")
migrate = flask_migrate.Migrate()
