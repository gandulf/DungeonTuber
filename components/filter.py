class FilterConfig:
    categories: dict[str, int] = {}
    tags: list[str] = []
    bpm: int | None = None
    genres: list[str] = []

    def __init__(self, categories={}, tags=[], bpm=None, genres=[]):
        self.categories = categories
        self.tags = tags
        self.bpm = bpm
        self.genres = genres

    def get_category(self, category_key: str, default: int = None) -> int:
        return self.categories.get(category_key, default)

    def toggle_tag(self, tag:str, state:int):
        if state == 0 and tag in self.tags:
            self.tags.remove(tag)
        elif tag not in self.tags:
            self.tags.append(tag)

    def toggle_genre(self, genre:str, state:int):
        if state == 0 and genre in self.genres:
            self.genres.remove(genre)
        elif genre not in self.genres:
            self.genres.append(genre)

    def empty(self) -> bool:
        empty = True
        for value in self.categories.values():
            if value is not None:
                empty = False
                break

        empty = empty and (self.tags is None or len(self.tags) == 0) and self.bpm is None and (self.genres is None or len(self.genres) == 0)

        return empty
