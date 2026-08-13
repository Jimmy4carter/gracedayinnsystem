import os
import sys

# Add the project root directory to the python path
sys.path.insert(0, os.path.dirname(__file__))

# Set the Django settings module for production
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gracedayinn.settings.prod")

# Expose the WSGI application for Passenger
from gracedayinn.wsgi import application
