"""EN/DE -> JA document translator using the DeepL API."""
from importlib.metadata import PackageNotFoundError, version

try:
    # pyproject.toml の version（インストール時のメタデータ）を唯一の定義元にする
    __version__ = version("deepl-translator")
except PackageNotFoundError:  # インストールせずにソースから直接読み込んだ場合
    __version__ = "0+unknown"
