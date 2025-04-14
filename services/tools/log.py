import logging

# Configure logging - just create the logger without handlers
# We'll add the RichHandler in main.py
logger = logging.getLogger("xo_template_generator")
logger.setLevel(logging.INFO)
# Don't propagate to root logger to avoid duplicate messages
logger.propagate = False
