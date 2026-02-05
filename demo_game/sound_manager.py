# sound_manager.py
from __future__ import annotations
from pathlib import Path
import pygame

class SoundManager:
    """
    Manages all game sound effects with volume control and pooling.
    """
    def __init__(self):
        pygame.mixer.init()
        
        # Sound effect storage
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        
        # Volume controls (0.0 to 1.0)
        self.master_volume = 0.7
        self.sfx_volume = 0.8
        
        # Load sounds
        self._load_sounds()
    
    def _load_sounds(self):
        """Load all sound effects from the sounds/ directory."""
        try:
            # Assuming sounds are in BRAINBUFF/sounds/
            project_root = Path(__file__).resolve().parents[1]
            sounds_dir = project_root / "sounds"
            
            # Define sound files to load
            sound_files = {
                "shoot": "shoot.wav",      # Player shoots projectile
                "enemy_die": "enemy_die.wav",  # Enemy dies
                "enemy_hit": "enemy_hit.wav",  # Enemy takes damage (optional)
                "player_hit": "player_hit.wav",  # Player takes damage (optional)
                "level_up": "level_up.wav",    # Player levels up (optional)
            }
            
            for key, filename in sound_files.items():
                sound_path = sounds_dir / filename
                if sound_path.exists():
                    self.sounds[key] = pygame.mixer.Sound(str(sound_path))
                    print(f"✓ Loaded sound: {key}")
                else:
                    print(f"✗ Sound not found: {sound_path}")
                    
        except Exception as e:
            print(f"Sound loading error: {e}")
    
    def play(self, sound_key: str, volume_override: float = None):
        """
        Play a sound effect.
        
        Args:
            sound_key: Key of the sound to play (e.g., 'shoot', 'enemy_die')
            volume_override: Optional volume override (0.0 to 1.0)
        """
        if sound_key not in self.sounds:
            return
        
        sound = self.sounds[sound_key]
        
        # Calculate final volume
        if volume_override is not None:
            volume = volume_override * self.master_volume
        else:
            volume = self.sfx_volume * self.master_volume
        
        sound.set_volume(volume)
        sound.play()
    
    def set_master_volume(self, volume: float):
        """Set master volume (0.0 to 1.0)."""
        self.master_volume = max(0.0, min(1.0, volume))
    
    def set_sfx_volume(self, volume: float):
        """Set sound effects volume (0.0 to 1.0)."""
        self.sfx_volume = max(0.0, min(1.0, volume))