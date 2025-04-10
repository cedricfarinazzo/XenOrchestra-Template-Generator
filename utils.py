import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('template_generator')

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