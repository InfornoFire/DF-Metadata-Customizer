"""Song metadata wrapper providing safe access and defaults."""

from pathlib import Path


class SongMetadata:
    """A wrapper around song metadata that provides safe access and defaults."""

    def __init__(self, data: dict, path: str, prefix: str = "", *, is_latest: bool = False) -> None:
        """Initialize SongMetadata."""
        self._data = data
        self.path = path
        self.prefix = prefix
        self._is_latest = is_latest

    def get(self, field: str) -> str:
        """Get value from metadata using properties or raw data."""
        f = field.lower()
        if f == "title":
            return self.title
        if f == "artist":
            return self.artist
        if f == "coverartist":
            return self.coverartist
        if f == "version":
            return self.version_str
        if f in ("disc", "discnumber"):
            return self.disc
        if f == "track":
            return self.track
        if f == "date":
            return self.date
        if f == "comment":
            return self.comment
        if f == "special":
            return self.special

        val = self._data.get(field)
        return str(val) if val is not None else ""

    @property
    def raw_data(self) -> dict:
        """Return the raw metadata dictionary."""
        return self._data

    @property
    def song_id(self) -> str:
        """Return a unique identifier for the song."""
        return f"{self.title}|{self.artist}|{self.coverartist}"

    @property
    def title(self) -> str:
        """Return the song title."""
        return self._data.get("Title") or Path(self.path).stem

    @property
    def artist(self) -> str:
        """Return the song artist."""
        return self._data.get("Artist") or ""

    @property
    def coverartist(self) -> str:
        """Return the cover artist."""
        return self._data.get("CoverArtist") or ""

    @property
    def version(self) -> float:
        """Return the song version as a float."""
        raw = self._data.get("Version", 0)
        try:
            return float(raw)
        except (ValueError, TypeError):
            return 0.0

    @property
    def version_str(self) -> str:
        """Return the song version as a string."""
        v = self.version
        return str(int(v)) if v.is_integer() else str(v)

    @property
    def disc(self) -> str:
        """Return the disc number."""
        return self._data.get("Discnumber") or ""

    @property
    def track(self) -> str:
        """Return the track number."""
        return self._data.get("Track") or ""

    @property
    def date(self) -> str:
        """Return the release date."""
        return self._data.get("Date") or ""

    @property
    def comment(self) -> str:
        """Return the song comment."""
        return self._data.get("Comment") or ""

    @property
    def special(self) -> str:
        """Return the special field value."""
        return self._data.get("Special") or ""

    @property
    def is_latest(self) -> bool:
        """Return whether this is the latest version."""
        return self._is_latest
