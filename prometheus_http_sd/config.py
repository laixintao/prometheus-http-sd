class Config:
    root_dir: str
    redis_url: str
    cache_expire_seconds: int
    stale_job_timeout_seconds: int
    stale_job_check_interval_seconds: int

    def __init__(self) -> None:
        self.root_dir = ""
        self.redis_url = "redis://localhost:6379/0"
        self.cache_expire_seconds = 300
        self.stale_job_timeout_seconds = 300
        self.stale_job_check_interval_seconds = 60


config = Config()
