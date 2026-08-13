import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b'GDIBACKUP1'
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16


def _derive_key(passphrase, salt):
    return Scrypt(salt=salt, length=32, n=2 ** 14, r=8, p=1).derive(passphrase.encode())


def encrypt_file(source, destination, passphrase):
    if len(passphrase) < 24:
        raise ValueError('BACKUP_ENCRYPTION_KEY must contain at least 24 characters.')
    salt, nonce = os.urandom(SALT_SIZE), os.urandom(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    with Path(source).open('rb') as incoming, Path(destination).open('wb+') as outgoing:
        outgoing.write(MAGIC + salt + nonce + (b'\0' * TAG_SIZE))
        for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
            outgoing.write(encryptor.update(chunk))
        outgoing.write(encryptor.finalize())
        outgoing.seek(len(MAGIC) + SALT_SIZE + NONCE_SIZE)
        outgoing.write(encryptor.tag)


def decrypt_file(source, destination, passphrase):
    with Path(source).open('rb') as incoming:
        if incoming.read(len(MAGIC)) != MAGIC:
            raise ValueError('Not a GraceDay Inn encrypted backup.')
        salt, nonce, tag = incoming.read(SALT_SIZE), incoming.read(NONCE_SIZE), incoming.read(TAG_SIZE)
        decryptor = Cipher(
            algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        with Path(destination).open('wb') as outgoing:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                outgoing.write(decryptor.update(chunk))
            outgoing.write(decryptor.finalize())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
