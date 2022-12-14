from settings import GlobalSettings, DbSettings


class DbStep:
    db_settings: DbSettings
    global_settings: GlobalSettings = GlobalSettings() # static

    def __init__(self, db_settings: DbSettings):
        self.db_settings = db_settings

    def run_step(self, settings: dict):
        raise NotImplementedError()
