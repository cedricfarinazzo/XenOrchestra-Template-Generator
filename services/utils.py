import logging

# Configure logging - just create the logger without handlers
# We'll add the RichHandler in main.py
logger = logging.getLogger('xo_template_generator')
logger.setLevel(logging.INFO)
# Don't propagate to root logger to avoid duplicate messages
logger.propagate = False

def get_version_name(distribution, version):
    """Get the version name for a distribution version."""
    if distribution.lower() == 'debian':
        version_map = {
            12: "Bookworm",
            11: "Bullseye",
            10: "Buster",
            9: "Stretch",
            8: "Jessie",
            7: "Wheezy"
        }
        return version_map.get(int(version), "Unknown")
    return "Unknown"