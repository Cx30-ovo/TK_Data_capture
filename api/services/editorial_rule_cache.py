"""Disposable local rule cache, separate from every business database.

Only the explicitly started background worker writes files. GET handlers call
read_many, which never creates directories or repairs corrupted cache entries.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
import time
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class EditorialRuleCache:
    def __init__(self, root, version, capacity=4096):
        self.root = Path(root) / digest(version)[:20]
        self.version = version
        self.capacity = capacity
        self.memory = OrderedDict()
        self.lock = Lock()

    def _path(self, ident):
        return self.root / (digest(["dy", ident]) + ".json")

    def _remember(self, ident, row):
        with self.lock:
            self.memory[ident] = deepcopy(row)
            self.memory.move_to_end(ident)
            while len(self.memory) > self.capacity:
                self.memory.popitem(last=False)

    def _read(self, ident, source_sha):
        with self.lock:
            row = deepcopy(self.memory.get(ident))
        if row is None:
            try:
                row = json.loads(self._path(ident).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        try:
            valid = (row["version"] == self.version and row["source_sha256"] == source_sha
                     and row["aweme_id"] == ident and isinstance(row["tags"], dict)
                     and row["tags"]["tag_rule_version"] == self.version
                     and row["tags"]["classification_source_sha256"] == source_sha
                     and row["payload_sha256"] == digest(row["tags"])
                     and isinstance(row["cached_at"], int))
        except (KeyError, TypeError):
            valid = False
        if not valid:
            return None
        self._remember(ident, row)
        return deepcopy(row)

    def read_many(self, sources):
        return {ident: row for ident, sha in sources
                if (row := self._read(ident, sha)) is not None}

    def save(self, ident, source_sha, tags):
        row = dict(version=self.version, aweme_id=ident, source_sha256=source_sha,
                   tags=deepcopy(tags), payload_sha256=digest(tags), cached_at=int(time.time()))
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(ident)
        temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self._remember(ident, row)
        return row
