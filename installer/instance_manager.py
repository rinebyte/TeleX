"""CRUD operations for TeleX multi-instance registry (~/.telex/instances.json)."""

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path

TELEX_HOME = Path.home() / ".telex"
INSTANCES_DIR = TELEX_HOME / "instances"
REGISTRY_PATH = TELEX_HOME / "instances.json"


@dataclass
class InstanceConfig:
    name: str
    api_id: int
    api_hash: str
    phone: str
    proxy_url: str = ""

    @property
    def work_dir(self) -> Path:
        return INSTANCES_DIR / self.name

    @property
    def env_path(self) -> Path:
        return self.work_dir / ".env"


def _ensure_dirs():
    TELEX_HOME.mkdir(exist_ok=True)
    INSTANCES_DIR.mkdir(exist_ok=True)


def load_instances() -> list[InstanceConfig]:
    """Read the instance registry."""
    if not REGISTRY_PATH.exists():
        return []
    data = json.loads(REGISTRY_PATH.read_text())
    return [InstanceConfig(**item) for item in data]


def save_instances(instances: list[InstanceConfig]):
    """Write the instance registry."""
    _ensure_dirs()
    REGISTRY_PATH.write_text(json.dumps([asdict(i) for i in instances], indent=2))


def add_instance(name: str, api_id: int, api_hash: str, phone: str, proxy_url: str = "") -> InstanceConfig:
    """Create a new instance: directory, .env, and registry entry."""
    instances = load_instances()

    if any(i.name == name for i in instances):
        raise ValueError(f"Instance '{name}' already exists")

    config = InstanceConfig(
        name=name,
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        proxy_url=proxy_url,
    )

    # Create work directory and .env
    config.work_dir.mkdir(parents=True, exist_ok=True)
    env_lines = [
        f"API_ID={api_id}",
        f"API_HASH={api_hash}",
        f"PHONE_NUMBER={phone}",
    ]
    if proxy_url:
        env_lines.append(f"PROXY_URL={proxy_url}")
    config.env_path.write_text("\n".join(env_lines) + "\n")

    # Restrict .env permissions
    config.env_path.chmod(0o600)

    instances.append(config)
    save_instances(instances)
    return config


def remove_instance(name: str):
    """Remove an instance: directory and registry entry."""
    instances = load_instances()
    instance = next((i for i in instances if i.name == name), None)
    if not instance:
        raise ValueError(f"Instance '{name}' not found")

    # Remove work directory
    if instance.work_dir.exists():
        shutil.rmtree(instance.work_dir)

    instances = [i for i in instances if i.name != name]
    save_instances(instances)
