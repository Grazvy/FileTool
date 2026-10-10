"""Domain errors raised by the services and translated to HTTP 400 by the API."""


class FileToolError(Exception):
    """Base class for errors caused by bad input rather than by a bug."""


class UnsupportedFormatError(FileToolError):
    """The uploaded file is not a supported input format."""


class ConversionError(FileToolError):
    """The requested conversion is not possible or failed on this input."""


class PdfError(FileToolError):
    """The PDF could not be read or the requested page operation is invalid."""


class UploadTooLargeError(FileToolError):
    """The uploaded file exceeds Config.MAX_UPLOAD_BYTES."""
