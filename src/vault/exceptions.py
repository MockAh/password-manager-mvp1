"""Excepciones de dominio del gestor de bóvedas.

Todas las excepciones de negocio están aquí.
Importar desde este módulo, no definir excepciones ad-hoc en otros módulos.
"""


class VaultLockedError(Exception):
    """Se lanza cuando se intenta operar sobre una bóveda bloqueada."""


class VaultAlreadyExistsError(Exception):
    """Se lanza al intentar crear una bóveda en una ruta que ya existe."""


class WrongPasswordError(Exception):
    """Se lanza cuando la contraseña maestra es incorrecta.

    También se lanza cuando el tag GCM falla (datos manipulados),
    ya que AEAD no distingue entre contraseña incorrecta y datos alterados.
    Esto es intencional: no filtrar información sobre el estado del archivo.
    """


class VaultCorruptError(Exception):
    """Se lanza cuando el archivo de bóveda está malformado o corrupto.

    Causas: JSON inválido, campos obligatorios ausentes,
    salt/nonce con tamaño incorrecto, versión no soportada.
    """


class EntryNotFoundError(Exception):
    """Se lanza cuando un ID de entrada no existe en la bóveda."""


class FolderNotFoundError(Exception):
    """Se lanza cuando un ID de carpeta no existe en la bóveda."""


class DuplicateFolderNameError(Exception):
    """Se lanza cuando ya existe una carpeta con el mismo nombre."""
