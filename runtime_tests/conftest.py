import os

# Synthetic secret for tests only; production reads COMMUNICATION_SECRET from Infisical.
os.environ.setdefault('COMMUNICATION_SECRET','a'*20+'b'*20)
