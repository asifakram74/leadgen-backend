try:
    import pgeocode
    print("pgeocode is installed")
except ImportError:
    print("pgeocode is not installed")

try:
    import uszipcode
    print("uszipcode is installed")
except ImportError:
    print("uszipcode is not installed")
