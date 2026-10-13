"""
MyLittleAnsible.
"""

import warnings

from cryptography.utils import CryptographyDeprecationWarning

# paramiko déclenche ce warning à l'import : on le coupe avant tout import
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
