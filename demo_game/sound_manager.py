# sound_manager.py
from __future__ import annotations
from pathlib import Path
import pygame

class SoundManager:
    def __init__(self):
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(32)

        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.master_volume = 0.7
        self.sfx_volume = 0.8

        self._reserved_channels: dict[str, pygame.mixer.Channel] = {}
        self._priority_sounds = {"enemy_die", "level_up", "player_hit"}

        self._setup_reserved_channels()
        self._load_sounds()

    def _setup_reserved_channels(self):
        for i, key in enumerate(self._priority_sounds):
            channel = pygame.mixer.Channel(i)
            self._reserved_channels[key] = channel

    def _load_sounds(self):
        try:
            project_root = Path(__file__).resolve().parents[1]
            sounds_dir = project_root / "sounds"

            sound_files = {
                "shoot": "shoot.wav",
                "enemy_die": "enemy_die.wav",
                "enemy_hit": "enemy_hit.wav",
                "player_hit": "player_hit.wav",
                "level_up": "level_up.wav",
            }

            for key, filename in sound_files.items():
                sound_path = sounds_dir / filename
                if sound_path.exists():
                    self.sounds[key] = pygame.mixer.Sound(str(sound_path))

        except Exception as e:
            print(f"Sound loading error: {e}")

    def play(self, sound_key: str, volume_override: float = None):
        if sound_key not in self.sounds:
            return

        sound = self.sounds[sound_key]

        if volume_override is not None:
            volume = volume_override * self.master_volume
        else:
            volume = self.sfx_volume * self.master_volume

        sound.set_volume(volume)

        if sound_key in self._reserved_channels:
            channel = self._reserved_channels[sound_key]
            channel.play(sound)
        else:
            sound.play()

    def play_immediate(self, sound_key: str, volume_override: float = None):
        if sound_key not in self.sounds:
            return

        sound = self.sounds[sound_key]

        if volume_override is not None:
            volume = volume_override * self.master_volume
        else:
            volume = self.sfx_volume * self.master_volume

        sound.set_volume(volume)

        if sound_key in self._reserved_channels:
            channel = self._reserved_channels[sound_key]
            channel.stop()
            channel.play(sound)
        else:
            channel = pygame.mixer.find_channel(True)
            if channel:
                channel.play(sound)
            else:
                sound.play()

    def set_master_volume(self, volume: float):
        self.master_volume = max(0.0, min(1.0, volume))

    def set_sfx_volume(self, volume: float):
        self.sfx_volume = max(0.0, min(1.0, volume))