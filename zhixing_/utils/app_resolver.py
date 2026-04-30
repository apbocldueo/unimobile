import yaml
import os

class AppResolver:
    _MAPPING = None

    @classmethod
    def load_mapping(cls, path="configs/app_mapping.yaml"):
        if cls._MAPPING is None:
            if not os.path.exists(path):
                cls._MAPPING = {} 
                print(f"The APP mapping file was not found: {path}")
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    cls._MAPPING = yaml.safe_load(f)

    @classmethod
    def resolve(cls, alias: str, platform: str, language: str) -> str:
        cls.load_mapping()
        
        if alias not in cls._MAPPING:
            return alias
            
        entry = cls._MAPPING[alias]
        key = f"{platform}_{language}"
        
        if key in entry:
            return entry[key]
        
        pkg_key = f"package_{platform}"
        if pkg_key in entry:
            return entry[pkg_key]
            
        return list(entry.values())[0]