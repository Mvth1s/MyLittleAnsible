"""
MyLittleAnsible.
"""

import warnings

# paramiko déclenche à l'import des warnings de dépréciation de sa
# dépendance cryptography (TripleDES...) : on les coupe avant tout import,
# en filtrant sur le module émetteur pour ne pas importer cryptography.
warnings.filterwarnings("ignore", module=r"paramiko(\.|$)")
