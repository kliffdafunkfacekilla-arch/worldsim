import os
import sys
import json
import time
import threading
import requests

# Configure Kivy window settings before any other Kivy imports
from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '768')
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.clock import Clock
from kivy.core.window import Window

# Server API and WS URLs
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
WS_URL = os.getenv("WS_URL", "ws://localhost:8000")

# ============================================================================
# MASTER CLIENT CODE
# ============================================================================

class NestedPlanetaryCoordinateEngine:
    """
    Handles movement on a 300x300 planetary grid using 4 nested tiers:
    - Tier 1: Local Tile (tile_x, tile_y) in [0, 19]
    - Tier 2: Screen (screen_x, screen_y) in [0, 4]
    - Tier 3: Region (region_x, region_y) in [0, 5]
    - Tier 4: Sector (sector_x, sector_y) in [0, 9]
    
    Total Planetary Coords:
    planetary_x = sector_x * 30 + region_x * 5 + screen_x
    planetary_y = sector_y * 30 + region_y * 5 + screen_y
    """
    def __init__(self, start_x=100, start_y=100, tile_x=10, tile_y=10):
        # Derive nested coordinates from planetary coordinate start
        self.sector_x = start_x // 30
        rem_x = start_x % 30
        self.region_x = rem_x // 5
        self.screen_x = rem_x % 5
        
        self.sector_y = start_y // 30
        rem_y = start_y % 30
        self.region_y = rem_y // 5
        self.screen_y = rem_y % 5
        
        self.tile_x = tile_x
        self.tile_y = tile_y
 
    def get_planetary_coords(self):
        px = self.sector_x * 30 + self.region_x * 5 + self.screen_x
        py = self.sector_y * 30 + self.region_y * 5 + self.screen_y
        return px, py

    def move(self, dx, dy):
        tile_x = self.tile_x + dx
        tile_y = self.tile_y + dy
        
        screen_x, screen_y = self.screen_x, self.screen_y
        region_x, region_y = self.region_x, self.region_y
        sector_x, sector_y = self.sector_x, self.sector_y
        
        # Cascade X axis
        if tile_x >= 20:
            tile_x = 0
            screen_x += 1
            if screen_x >= 5:
                screen_x = 0
                region_x += 1
                if region_x >= 6:
                    region_x = 0
                    sector_x += 1
        elif tile_x < 0:
            tile_x = 19
            screen_x -= 1
            if screen_x < 0:
                screen_x = 4
                region_x -= 1
                if region_x < 0:
                    region_x = 5
                    sector_x -= 1
                    
        # Cascade Y axis
        if tile_y >= 20:
            tile_y = 0
            screen_y += 1
            if screen_y >= 5:
                screen_y = 0
                region_y += 1
                if region_y >= 6:
                    region_y = 0
                    sector_y += 1
        elif tile_y < 0:
            tile_y = 19
            screen_y -= 1
            if screen_y < 0:
                screen_y = 4
                region_y -= 1
                if region_y < 0:
                    region_y = 5
                    sector_y -= 1

        # Check planetary boundaries [0, 299]
        px = sector_x * 30 + region_x * 5 + screen_x
        py = sector_y * 30 + region_y * 5 + screen_y
        
        if 0 <= px < 300 and 0 <= py < 300:
            self.tile_x = tile_x
            self.tile_y = tile_y
            self.screen_x = screen_x
            self.screen_y = screen_y
            self.region_x = region_x
            self.region_y = region_y
            self.sector_x = sector_x
            self.sector_y = sector_y
            return True
        return False


class SimulationCanvas(Widget):
    """
    Left panel rendering the 15x11 view grid with smooth camera scrolls.
    Uses low-level Kivy graphics instructions for performance.
    """
    def __init__(self, coord_engine, shared_data, data_lock, elevation_data, **kwargs):
        super().__init__(**kwargs)
        self.coord_engine = coord_engine
        self.shared_data = shared_data
        self.data_lock = data_lock
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        
        # Calculate cell bounds and scroll offset
        w, h = self.size
        px, py = self.coord_engine.get_planetary_coords()
        tile_x = self.coord_engine.tile_x
        tile_y = self.coord_engine.tile_y
        
        tile_w = w / 15.0
        tile_h = h / 11.0
        
        with self.canvas:
            for col in range(-1, 16):
                for row in range(-1, 12):
                    cx = px + (col - 7)
                    cy = py + (row - 5)
                    
                    x_pos = self.x + (col - (tile_x / 20.0)) * tile_w
                    y_pos = self.y + (row - (tile_y / 20.0)) * tile_h
                    
                    if 0 <= cx < 300 and 0 <= cy < 300:
                        cell_id = cy * 300 + cx + 1
                        
                        active_tag = None
                        with self.data_lock:
                            if cell_id in self.shared_data["cache"]:
                                active_tag = self.shared_data["cache"][cell_id].get("active_chaos_tag")
                        
                        # Determine biome dynamically
                        app = App.get_running_app()
                        elev = 500.0
                        temp = 15.0
                        moist = 0.5
                        if app:
                            try:
                                elev = app.elevation_data[cx][cy]
                                temp = app.temperature_data[cx][cy]
                                moist = app.moisture_data[cx][cy]
                            except IndexError:
                                pass
                        
                        # Determine biome dynamically
                        biome = app.classify_biome(elev, temp, moist) if app else "Grasslands"
                        tile_image = app.get_tile_variant(biome, cx, cy) if app else None
                        
                        if active_tag and any(tag in active_tag for tag in ["#Mass", "#Flux", "#Omen", "#Epicenter", "#Vita"]):
                            # Shift the color tint on existing tiles to a purple, pink, or red color
                            if "#Flux" in active_tag:
                                Color(0.8, 0.2, 1.0, 1.0)  # Purple
                            elif "#Vita" in active_tag:
                                Color(1.0, 0.4, 0.8, 1.0)  # Pink
                            else:  # #Mass, #Epicenter, #Omen, etc.
                                Color(1.0, 0.2, 0.2, 1.0)  # Red
                        else:
                            if tile_image:
                                Color(1.0, 1.0, 1.0, 1.0)
                            else:
                                if biome == "ocean":
                                    Color(0.1, 0.3, 0.8, 1.0)
                                elif biome == "coast":
                                    Color(0.2, 0.5, 0.9, 1.0)
                                elif biome == "mountain":
                                    Color(0.5, 0.5, 0.5, 1.0)
                                elif biome == "tundra":
                                    Color(0.85, 0.85, 0.9, 1.0)
                                elif biome == "desert":
                                    Color(0.85, 0.75, 0.45, 1.0)
                                elif biome == "forest":
                                    Color(0.05, 0.4, 0.05, 1.0)
                                else:
                                    Color(0.15, 0.55, 0.15, 1.0)
                        
                        if tile_image:
                            Rectangle(pos=(x_pos + 1, y_pos + 1), size=(tile_w - 2, tile_h - 2), source=tile_image)
                        else:
                            Rectangle(pos=(x_pos + 1, y_pos + 1), size=(tile_w - 2, tile_h - 2))
                    else:
                        Color(0.05, 0.05, 0.08, 1.0)
                        Rectangle(pos=(x_pos + 1, y_pos + 1), size=(tile_w - 2, tile_h - 2))
            
            gold_x = self.x + 7.5 * tile_w
            gold_y = self.y + 5.5 * tile_h
            
            # Player coordinate indicator rendered last (highest Z-index) using player_sprite.png
            Color(1.0, 1.0, 1.0, 1.0)
            player_sprite_path = os.path.abspath(os.path.join("assets", "sprites", "player_sprite.png"))
            Rectangle(pos=(gold_x - tile_w * 0.15, gold_y - tile_h * 0.15), size=(tile_w * 0.3, tile_h * 0.3), source=player_sprite_path)


class HUDPanel(BoxLayout):
    """
    Right panel BoxLayout HUD containing dynamic text labels for clocks, coordinates,
    biome environmental stats, shadow metrics, character pools, and combat/hazard trigger.
    """
    def __init__(self, coord_engine, shared_data, data_lock, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.coord_engine = coord_engine
        self.shared_data = shared_data
        self.data_lock = data_lock
        
        self.padding = [15, 15, 15, 15]
        self.spacing = 10
        
        with self.canvas.before:
            Color(0.12, 0.12, 0.15, 1.0)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_rect, size=self.update_rect)
        
        self.add_widget(Label(
            text="[b][color=ffaa00]PLANETARY ENGINE HUD[/color][/b]",
            markup=True,
            font_size='18sp',
            size_hint_y=None,
            height=40
        ))
        
        self.status_label = Label(
            text="Status: [color=ff0000]OFFLINE[/color]",
            markup=True,
            font_size='14sp',
            size_hint_y=None,
            height=25
        )
        self.add_widget(self.status_label)
        
        self.clock_label = Label(
            text="System Clock:\n[color=888888]Loading...[/color]",
            markup=True,
            font_size='13sp',
            size_hint_y=None,
            height=45
        )
        self.add_widget(self.clock_label)
        
        self.position_label = Label(
            text="Position:\nPlanetary Coords: (--, --)\nTile: (--, --)",
            markup=True,
            font_size='13sp',
            size_hint_y=None,
            height=60
        )
        self.add_widget(self.position_label)
        
        self.hierarchy_label = Label(
            text="4-Tier Coordinate Hierarchy:\nSector: (-,-) | Region: (-,-)\nScreen: (-,-) | Tile: (-,-)",
            markup=True,
            font_size='11sp',
            size_hint_y=None,
            height=50
        )
        self.add_widget(self.hierarchy_label)
        
        self.biome_label = Label(
            text="Biome & Climate:\nElevation: ---\nTemp: ---\nMoisture: ---\nFlora Biomass: ---\nChaos Tag: ---",
            markup=True,
            font_size='12sp',
            size_hint_y=None,
            height=90
        )
        self.add_widget(self.biome_label)
        
        self.shadow_label = Label(
            text="Shadow Underworld Metrics:\nCult Infiltration: ---\nWarden Presence: ---",
            markup=True,
            font_size='12sp',
            size_hint_y=None,
            height=60
        )
        self.add_widget(self.shadow_label)
        
        self.character_label = Label(
            text="Player character:\n[color=888888]Loading...[/color]\nHealth: ---\nStamina: ---\nComposure: ---\nFocus: ---\nTrauma: ---\nChaos Exposure: ---\nMutations: ---",
            markup=True,
            font_size='11sp',
            size_hint_y=None,
            height=140
        )
        self.add_widget(self.character_label)
        
        self.damage_btn = Button(
            text="Trigger Hazard (Damage)",
            size_hint_y=None,
            height=35,
            background_color=(0.8, 0.2, 0.2, 1.0)
        )
        self.damage_btn.bind(on_release=self.on_damage_click)
        self.add_widget(self.damage_btn)
        
        self.add_widget(Widget())

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_damage_click(self, instance):
        app = App.get_running_app()
        if app:
            app.trigger_hazard_damage()

    def update_hud(self):
        px, py = self.coord_engine.get_planetary_coords()
        tile_x = self.coord_engine.tile_x
        tile_y = self.coord_engine.tile_y
        
        self.position_label.text = (
            f"Position:\n"
            f"[color=ffffff]Planetary Coords:[/color] [color=ffff00]({px}, {py})[/color]\n"
            f"[color=ffffff]Local Tile:[/color] [color=ffff00]({tile_x}, {tile_y})[/color]"
        )
        
        self.hierarchy_label.text = (
            f"4-Tier Coordinate Hierarchy:\n"
            f"[color=aaaaaa]Sector:[/color] ({self.coord_engine.sector_x}, {self.coord_engine.sector_y}) | "
            f"[color=aaaaaa]Region:[/color] ({self.coord_engine.region_x}, {self.coord_engine.region_y})\n"
            f"[color=aaaaaa]Screen:[/color] ({self.coord_engine.screen_x}, {self.coord_engine.screen_y}) | "
            f"[color=aaaaaa]Tile:[/color] ({tile_x}, {tile_y})"
        )
        
        with self.data_lock:
            connected = self.shared_data["connected"]
            clock = self.shared_data["clock"]
            chaos_context = self.shared_data["chaos_context"]
            shadow_intel = self.shared_data["shadow_intel"]
            cell_detail = self.shared_data["cell_detail"]
            char_data = self.shared_data.get("character")
            
        app = App.get_running_app()
        if char_data and app:
            app.character_id = char_data["character_id"]
            app.character_name = char_data["character_name"]
            app.character_health = char_data["health"]
            app.character_stamina = char_data["stamina"]
            app.character_composure = char_data["composure"]
            app.character_focus = char_data["focus"]
            app.character_trauma = char_data["trauma"]
            app.personal_chaos_exposure = char_data.get("personal_chaos_exposure", 0.0)
            app.mutations = char_data.get("mutations", [])
            
            max_caps = char_data.get("max_capacities", {})
            app.max_health = max_caps.get("max_health", 15)
            app.max_stamina = max_caps.get("max_stamina", 12)
            app.max_composure = max_caps.get("max_composure", 11)
            app.max_focus = max_caps.get("max_focus", 10)
            
        if app:
            muts_str = ", ".join(app.mutations) if app.mutations else "None"
            self.character_label.text = (
                f"Player character: [color=ffaa00]{app.character_name}[/color]\n"
                f"[color=ffffff]Health:[/color] [color=ff3333]{app.character_health}[/color] / {app.max_health}\n"
                f"[color=ffffff]Stamina:[/color] [color=ffff33]{app.character_stamina}[/color] / {app.max_stamina}\n"
                f"[color=ffffff]Composure:[/color] [color=33ffff]{app.character_composure}[/color] / {app.max_composure}\n"
                f"[color=ffffff]Focus:[/color] [color=ff33ff]{app.character_focus}[/color] / {app.max_focus}\n"
                f"[color=ffffff]Trauma:[/color] [color=ffaa55]{app.character_trauma}[/color]\n"
                f"[color=ffffff]Chaos Exposure:[/color] [color=ffaa00]{app.personal_chaos_exposure:.2f}[/color]\n"
                f"[color=ffffff]Mutations:[/color] [color=ff55ff]{muts_str}[/color]"
            )

        if connected:
            self.status_label.text = "Status: [color=00ff00]ONLINE[/color]"
            
            if clock:
                self.clock_label.text = (
                    f"System Clock:\n"
                    f"[color=00ffff]Year {clock.get('current_year', 1)}, Day {clock.get('current_day', 1)}, Segment {clock.get('current_segment', 0)}[/color]"
                )
                
            elevation_str = "---"
            temp_str = "---"
            moisture_str = "---"
            flora_str = "---"
            chaos_str = "[color=aaaaaa]StableReality[/color]"
            
            if cell_detail:
                elevation_str = f"{float(cell_detail.get('elevation_meters', 0.0)):.1f} m"
                temp_str = f"{float(cell_detail.get('temperature_celsius', 0.0)):.1f}°C"
                moisture_str = f"{float(cell_detail.get('moisture_index', 0.0)):.3f}"
                
                flora_data = cell_detail.get("flora_biomass_data") or {}
                if isinstance(flora_data, str):
                    try:
                        flora_data = json.loads(flora_data)
                    except:
                        flora_data = {}
                biomass = flora_data.get("biomass_index", flora_data.get("biomass_volume", 0.0))
                flora_str = f"{biomass:.2f}"
                
            if chaos_context:
                active_tag = chaos_context.get("active_tag") or "StableReality"
                if "#Epicenter" in active_tag:
                    chaos_str = f"[color=ff3333]{active_tag}[/color]"
                elif "#Flux" in active_tag:
                    chaos_str = f"[color=33ffff]{active_tag}[/color]"
                elif "#Vita" in active_tag:
                    chaos_str = f"[color=33ff33]{active_tag}[/color]"
                else:
                    chaos_str = f"[color=aaaaaa]{active_tag}[/color]"
                    
            self.biome_label.text = (
                f"Biome & Climate:\n"
                f"[color=ffffff]Elevation:[/color] {elevation_str}\n"
                f"[color=ffffff]Temp:[/color] {temp_str}\n"
                f"[color=ffffff]Moisture:[/color] {moisture_str}\n"
                f"[color=ffffff]Flora Presence:[/color] {flora_str}\n"
                f"[color=ffffff]Chaos Tag:[/color] {chaos_str}"
            )
            
            cult_str = "0.00"
            warden_str = "0.00"
            if shadow_intel:
                exact_cult = shadow_intel.get("exact_cult_index", 0.0)
                exact_warden = shadow_intel.get("exact_warden_index", 0.0)
                
                if exact_cult > 0.6:
                    cult_str = f"[color=ff3333]{exact_cult:.2f}[/color]"
                elif exact_cult > 0.25:
                    cult_str = f"[color=ff9900]{exact_cult:.2f}[/color]"
                else:
                    cult_str = f"[color=33ff33]{exact_cult:.2f}[/color]"
                    
                warden_str = f"[color=33ffff]{exact_warden:.2f}[/color]"
                
            self.shadow_label.text = (
                f"Shadow Underworld Metrics:\n"
                f"[color=ffffff]Cult Infiltration:[/color] {cult_str}\n"
                f"[color=ffffff]Warden Presence:[/color] {warden_str}"
            )
        else:
            self.status_label.text = "Status: [color=ff0000]OFFLINE[/color]"
            self.clock_label.text = "System Clock:\n[color=888888]Disconnected[/color]"
            self.biome_label.text = "Biome & Climate:\n[color=888888]Disconnected[/color]"
            self.shadow_label.text = "Shadow Underworld Metrics:\n[color=888888]Disconnected[/color]"


class SimulationClientApp(App):
    """
    Main Kivy desktop client application. Sets up UI layouts, binds W,A,S,D controls,
    and runs the background async API heartbeat updates.
    """
    def build(self):
        self.title = "Planetary Simulation client"
        
        # Player pools initialization
        self.character_id = None
        self.character_name = "Loading..."
        self.character_health = 15
        self.character_stamina = 12
        self.character_composure = 11
        self.character_focus = 10
        self.character_trauma = 0
        self.personal_chaos_exposure = 0.0
        self.mutations = []
        self.max_health = 15
        self.max_stamina = 12
        self.max_composure = 11
        self.max_focus = 10
        
        # Load tile variants
        BIOMES = ["Grasslands", "Interior_floors", "coast", "desert", "forest", "mountain", "ocean", "tundra"]
        self.biome_tiles = {}
        for b in BIOMES:
            b_path = os.path.join("assets", "tiles", b)
            if os.path.isdir(b_path):
                self.biome_tiles[b] = [
                    os.path.join(b_path, f) for f in os.listdir(b_path)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                ]
            else:
                self.biome_tiles[b] = []
        
        # Fetch/seed character details from server
        try:
            r = requests.post(f"{SERVER_URL}/api/player/get-or-create", timeout=4.0)
            if r.status_code == 200:
                char_data = r.json()
                self.character_id = char_data["character_id"]
                self.character_name = char_data["character_name"]
                self.character_health = char_data["health"]
                self.character_stamina = char_data["stamina"]
                self.character_composure = char_data["composure"]
                self.character_focus = char_data["focus"]
                self.character_trauma = char_data["trauma"]
                self.personal_chaos_exposure = char_data.get("personal_chaos_exposure", 0.0)
                self.mutations = char_data.get("mutations", [])
                print(f"Loaded character {self.character_name} ({self.character_id}) from PostgreSQL.")
        except Exception as e:
            print(f"Warning: Failed to fetch character on boot: {e}")
            self.character_id = "00000000-0000-0000-0000-000000000000"
            self.character_name = "Offline Hero"
        
        # Coordinates engine initialization
        self.coord_engine = NestedPlanetaryCoordinateEngine(start_x=100, start_y=100, tile_x=10, tile_y=10)
        
        # Localized memory cache dictionary
        self.data_lock = threading.Lock()
        self.shared_data = {
            "connected": False,
            "clock": None,
            "chaos_context": None,
            "shadow_intel": None,
            "cell_detail": None,
            "character": None,
            "cache": {}
        }
        
        self.elevation_data = [[0.0 for _ in range(300)] for _ in range(300)]
        self.temperature_data = [[15.0 for _ in range(300)] for _ in range(300)]
        self.moisture_data = [[0.5 for _ in range(300)] for _ in range(300)]
        self.crust_mesh_loaded = False
        self.is_fetching = False
        
        root_layout = BoxLayout(orientation='horizontal')
        
        # Left canvas (75%)
        self.canvas_widget = SimulationCanvas(
            coord_engine=self.coord_engine,
            shared_data=self.shared_data,
            data_lock=self.data_lock,
            elevation_data=self.elevation_data,
            size_hint=(0.75, 1.0)
        )
        root_layout.add_widget(self.canvas_widget)
        
        # Right HUD Panel (25%)
        self.hud_widget = HUDPanel(
            coord_engine=self.coord_engine,
            shared_data=self.shared_data,
            data_lock=self.data_lock,
            size_hint=(0.25, 1.0)
        )
        root_layout.add_widget(self.hud_widget)
        
        threading.Thread(target=self.download_crust_mesh, daemon=True).start()
        Window.bind(on_key_down=self._on_keyboard_down)
        Clock.schedule_interval(self.heartbeat_tick, 0.5)
        Clock.schedule_interval(self.update_ui, 1.0 / 60.0)
        
        return root_layout

    def classify_biome(self, elevation, temp, moisture):
        if elevation < -50.0:
            return "ocean"
        elif elevation < 0.0:
            return "coast"
        elif elevation > 1800.0:
            return "mountain"
        else:
            if temp < 2.0:
                return "tundra"
            if moisture < 0.25 or (moisture < 0.5 and temp > 25.0):
                return "desert"
            if moisture >= 0.55:
                return "forest"
            return "Grasslands"

    def get_tile_variant(self, biome, cx, cy):
        variants = self.biome_tiles.get(biome, [])
        if not variants:
            return None
        idx = (cx * 17 + cy * 31) % len(variants)
        return os.path.abspath(variants[idx])

    def trigger_hazard_damage(self):
        if not self.character_id or self.character_id == "00000000-0000-0000-0000-000000000000":
            print("Cannot trigger damage: No valid character loaded.")
            return

        new_health = max(0, self.character_health - 1)
        payload = {
            "character_id": self.character_id,
            "health": new_health,
            "stamina": self.character_stamina,
            "composure": self.character_composure,
            "focus": self.character_focus,
            "trauma": self.character_trauma,
            "personal_chaos_exposure": self.personal_chaos_exposure,
            "mutations": self.mutations
        }

        print(f"Hazard Event: Damaging player. Firing secure sync payload: {payload}")
        try:
            r = requests.post(f"{SERVER_URL}/api/player/update-pools", json=payload, timeout=3.0)
            if r.status_code == 200:
                print("Server response: Health pool successfully updated in PostgreSQL database.")
                res_data = r.json()
                self.character_health = res_data["health"]
                self.character_stamina = res_data["stamina"]
                self.character_composure = res_data["composure"]
                self.character_focus = res_data["focus"]
                self.personal_chaos_exposure = res_data["personal_chaos_exposure"]
                self.mutations = res_data["mutations"]
            else:
                print(f"Error: Server rejected pool update with status {r.status_code}")
        except Exception as e:
            print(f"Error: Connection failed during pool update sync: {e}")

    def download_crust_mesh(self):
        print(f"Downloading world crust mesh...")
        try:
            r = requests.get(f"{SERVER_URL}/api/world-map/crust-mesh", timeout=15.0)
            if r.status_code == 200:
                data = r.json()
                temp_elev = [[0.0 for _ in range(300)] for _ in range(300)]
                temp_temp = [[15.0 for _ in range(300)] for _ in range(300)]
                temp_moist = [[0.5 for _ in range(300)] for _ in range(300)]
                for cell in data:
                    cx = cell["coord_x"]
                    cy = cell["coord_y"]
                    elev = cell["elevation_meters"]
                    temp = cell["temperature_celsius"]
                    moist = cell["moisture_index"]
                    if 0 <= cx < 300 and 0 <= cy < 300:
                        temp_elev[cx][cy] = elev
                        temp_temp[cx][cy] = temp
                        temp_moist[cx][cy] = moist
                
                with self.data_lock:
                    self.elevation_data[:] = temp_elev
                    self.temperature_data[:] = temp_temp
                    self.moisture_data[:] = temp_moist
                    self.crust_mesh_loaded = True
                print("World crust mesh cached successfully.")
        except Exception as e:
            print(f"Warning: Failed to fetch crust mesh: {e}. Defaulting to flat terrain.")

    def heartbeat_tick(self, dt):
        if self.is_fetching:
            return
        self.is_fetching = True
        threading.Thread(target=self.fetch_server_state_thread, daemon=True).start()

    def fetch_server_state_thread(self):
        try:
            px, py = self.coord_engine.get_planetary_coords()
            cell_id = py * 300 + px + 1
            
            r_clock = requests.get(f"{SERVER_URL}/api/world-state", timeout=2.0)
            clock_data = r_clock.json() if r_clock.status_code == 200 else None
            
            r_chaos = requests.get(f"{SERVER_URL}/api/cell/{cell_id}/chaos-context", timeout=2.0)
            chaos_data = r_chaos.json() if r_chaos.status_code == 200 else None
            
            r_shadow = requests.get(f"{SERVER_URL}/api/cell/{cell_id}/shadow-intel", timeout=2.0)
            shadow_data = r_shadow.json() if r_shadow.status_code == 200 else None
            
            r_cell = requests.get(f"{SERVER_URL}/api/cell/{cell_id}", timeout=2.0)
            cell_detail = r_cell.json() if r_cell.status_code == 200 else None
            
            character_data = None
            if self.character_id and self.character_id != "00000000-0000-0000-0000-000000000000":
                r_char = requests.get(f"{SERVER_URL}/api/player/character/{self.character_id}", timeout=2.0)
                if r_char.status_code == 200:
                    character_data = r_char.json()
            else:
                r_char = requests.post(f"{SERVER_URL}/api/player/get-or-create", timeout=2.0)
                if r_char.status_code == 200:
                    character_data = r_char.json()
            
            with self.data_lock:
                self.shared_data["connected"] = True
                self.shared_data["clock"] = clock_data
                self.shared_data["chaos_context"] = chaos_data
                self.shared_data["shadow_intel"] = shadow_data
                self.shared_data["cell_detail"] = cell_detail
                self.shared_data["character"] = character_data
                
                if chaos_data and shadow_data:
                    self.shared_data["cache"][cell_id] = {
                        "active_chaos_tag": chaos_data.get("active_tag"),
                        "subversion": shadow_data.get("exact_cult_index", 0.0),
                        "infiltration": shadow_data.get("exact_warden_index", 0.0)
                    }
        except Exception as e:
            with self.data_lock:
                self.shared_data["connected"] = False
        finally:
            self.is_fetching = False

    def _on_keyboard_down(self, window, key, scancode, codepoint, modifiers):
        dx, dy = 0, 0
        if codepoint == 'w' or key == 273 or key == 119:
            dy = 1
        elif codepoint == 's' or key == 274 or key == 115:
            dy = -1
        elif codepoint == 'a' or key == 276 or key == 97:
            dx = -1
        elif codepoint == 'd' or key == 275 or key == 100:
            dx = 1
        else:
            return True
            
        if dx != 0 or dy != 0:
            moved = self.coord_engine.move(dx, dy)
            if moved:
                self.canvas_widget.redraw()
                self.hud_widget.update_hud()
        return True

    def update_ui(self, dt):
        self.canvas_widget.redraw()
        self.hud_widget.update_hud()


# ============================================================================
# PLANETARY BUILDER ADMIN EDITOR INTERFACE
# ============================================================================

class BuilderCanvas(Widget):
    """
    Top-down grid canvas mapping 300x300 macro cells.
    Uses hardware-accelerated 300x300 Texture blit for smooth 60 FPS rendering.
    Maps mouse click & drag events to cell indexes and logs them in the drag buffer.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.texture = Texture.create(size=(300, 300), colorfmt='rgb')
        self.texture.mag_filter = 'nearest'
        self.texture.min_filter = 'nearest'
        self.bind(pos=self.redraw, size=self.redraw)
        
    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(1.0, 1.0, 1.0, 1.0)
            Rectangle(pos=self.pos, size=self.size, texture=self.texture)
            
    def update_texture(self):
        app = App.get_running_app()
        if not app:
            return
            
        buf = bytearray(300 * 300 * 3)
        with app.data_lock:
            for y in range(300):
                for x in range(300):
                    idx = (y * 300 + x) * 3
                    
                    if (x, y) in app.drag_buffer:
                        # Highlight cell in drag buffer (yellow paint feedback)
                        buf[idx] = 255
                        buf[idx+1] = 255
                        buf[idx+2] = 0
                        continue
                        
                    active_tag = app.chaos_tags[x][y]
                    if active_tag and any(tag in active_tag for tag in ["#Mass", "#Flux", "#Omen", "#Epicenter", "#Vita"]):
                        if "#Flux" in active_tag:
                            buf[idx] = 204
                            buf[idx+1] = 51
                            buf[idx+2] = 255
                        elif "#Vita" in active_tag:
                            buf[idx] = 255
                            buf[idx+1] = 102
                            buf[idx+2] = 204
                        else:
                            buf[idx] = 255
                            buf[idx+1] = 51
                            buf[idx+2] = 51
                        continue
                        
                    # Standard height color representation
                    h = app.elevation_data[x][y]
                    if h < -50.0:  # Deep Ocean
                        buf[idx] = 25
                        buf[idx+1] = 75
                        buf[idx+2] = 200
                    elif h < 0.0:  # Coast Water
                        buf[idx] = 50
                        buf[idx+1] = 125
                        buf[idx+2] = 225
                    elif h > 1800.0:  # Mountains
                        buf[idx] = 120
                        buf[idx+1] = 120
                        buf[idx+2] = 120
                    else:  # Biome land mappings
                        t = app.temperature_data[x][y]
                        m = app.moisture_data[x][y]
                        
                        if t < 2.0:  # Tundra
                            buf[idx] = 210
                            buf[idx+1] = 210
                            buf[idx+2] = 230
                        elif m < 0.25 or (m < 0.5 and t > 25.0):  # Desert
                            buf[idx] = 220
                            buf[idx+1] = 190
                            buf[idx+2] = 110
                        elif m >= 0.55:  # Forest
                            buf[idx] = 10
                            buf[idx+1] = 100
                            buf[idx+2] = 10
                        else:  # Grasslands
                            buf[idx] = 35
                            buf[idx+1] = 140
                            buf[idx+2] = 35
                            
        self.texture.blit_buffer(bytes(buf), colorfmt='rgb', bufferfmt='ubyte')
        self.redraw()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.track_touch(touch)
            return True
        return False

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos):
            self.track_touch(touch)
            return True
        return False

    def on_touch_up(self, touch):
        app = App.get_running_app()
        if app and app.drag_buffer:
            # Trigger paint transaction
            app.dispatch_paint_stroke()
            return True
        return False

    def track_touch(self, touch):
        app = App.get_running_app()
        if not app:
            return
            
        # Translate touch coordinate to 300x300 grid coords
        local_x = touch.x - self.x
        local_y = touch.y - self.y
        
        grid_x = int((local_x / self.width) * 300)
        grid_y = int((local_y / self.height) * 300)
        
        # Clamp to bounds
        grid_x = max(0, min(299, grid_x))
        grid_y = max(0, min(299, grid_y))
        
        # Add to paint buffer based on brush size
        brush_size = getattr(app, 'brush_size', 1)
        radius = (brush_size - 1) / 2.0
        
        with app.data_lock:
            if brush_size <= 1:
                app.drag_buffer.add((grid_x, grid_y))
            else:
                for dx in range(-brush_size, brush_size + 1):
                    for dy in range(-brush_size, brush_size + 1):
                        if (dx*dx + dy*dy) <= (radius + 0.1) * (radius + 0.1):
                            nx, ny = grid_x + dx, grid_y + dy
                            if 0 <= nx < 300 and 0 <= ny < 300:
                                app.drag_buffer.add((nx, ny))
                                
        self.update_texture()


class WSConfigClient:
    """
    Thread-safe WebSocket Client connecting to the FastAPI /api/builder/ws hot-reloader.
    Sends config APPLY_TEMPLATE payloads without blocking the Kivy GUI thread.
    """
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.lock = threading.Lock()
        
    def connect(self):
        import websocket
        try:
            self.ws = websocket.create_connection(f"{self.ws_url}/api/builder/ws", timeout=3.0)
            print("Successfully connected to FastAPI builder config WebSocket.")
        except Exception as e:
            print(f"WS Connection failed: {e}")
            self.ws = None
            
    def send_config(self, config_dict):
        threading.Thread(target=self._send_thread, args=(config_dict,), daemon=True).start()
        
    def _send_thread(self, config_dict):
        with self.lock:
            if not self.ws:
                self.connect()
            if self.ws:
                try:
                    payload = {
                        "action": "APPLY_TEMPLATE",
                        "config": config_dict
                    }
                    self.ws.send(json.dumps(payload))
                    resp = self.ws.recv()
                    print(f"Config WS Reloaded: {resp}")
                except Exception as e:
                    print(f"WS Send failed: {e}")
                    self.ws = None


class PlanetaryBuilderDashboardApp(App):
    """
    Planetary Map Builder Administration Interface.
    Fires bulk OpenSimplex seeds, provides paint stroke buffers,
    and hot-reloads parameter configurations in real time via WebSockets.
    """
    def build(self):
        self.title = "Planetary Simulation - Admin Builder Dashboard"
        
        # Grid variables initialization
        self.elevation_data = [[0.0 for _ in range(300)] for _ in range(300)]
        self.temperature_data = [[15.0 for _ in range(300)] for _ in range(300)]
        self.moisture_data = [[0.5 for _ in range(300)] for _ in range(300)]
        self.chaos_tags = [[None for _ in range(300)] for _ in range(300)]
        
        self.drag_buffer = set()
        self.data_lock = threading.Lock()
        self.is_seeding = False
        
        # Brushes definitions
        self.active_brush = {
            "type": "climate_override",
            "name": "Grasslands",
            "elevation": 500.0,
            "temperature": 20.0,
            "moisture": 0.4,
            "chaos_tag": None
        }
        
        # Config initial loading from config.json
        self.config_data = {
            "time_scale_multiplier": 1,
            "fauna_base_reproduction_rate": 1.0,
            "mutation_threshold": 90.0,
            "flora_base_growth_rate": 1.0
        }
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    self.config_data = json.load(f)
                print(f"Loaded config.json: {self.config_data}")
            except Exception as e:
                print(f"Failed to read config.json: {e}")
                
        # Initialize WS Client
        self.ws_client = WSConfigClient(WS_URL)
        
        # Root layout
        root_layout = BoxLayout(orientation='horizontal')
        
        # Left paint canvas (70%)
        self.builder_canvas = BuilderCanvas(size_hint=(0.7, 1.0))
        root_layout.add_widget(self.builder_canvas)
        
        # Right sidebar parameters / brushes (30%)
        sidebar_scroll = ScrollView(size_hint=(0.3, 1.0))
        sidebar_layout = BoxLayout(orientation='vertical', spacing=8, padding=12, size_hint_y=None)
        sidebar_layout.bind(minimum_height=sidebar_layout.setter('height'))
        
        with sidebar_layout.canvas.before:
            Color(0.08, 0.08, 0.1, 1.0)
            self.rect = Rectangle(pos=sidebar_layout.pos, size=sidebar_layout.size)
        sidebar_layout.bind(pos=self._update_sidebar_rect, size=self._update_sidebar_rect)
        
        # Title Label
        sidebar_layout.add_widget(Label(
            text="[b][color=00ffcc]PLANETARY BUILDER[/color][/b]",
            markup=True, font_size='18sp', size_hint_y=None, height=35
        ))
        
        # Generation Button
        self.seed_btn = Button(
            text="Generate Base Crust",
            size_hint_y=None, height=40,
            background_color=(0.1, 0.6, 0.8, 1.0)
        )
        self.seed_btn.bind(on_release=self.on_seed_click)
        sidebar_layout.add_widget(self.seed_btn)
        
        # Brush Settings Section
        sidebar_layout.add_widget(Label(
            text="[b][color=ffffff]Brush Settings[/color][/b]",
            markup=True, font_size='13sp', size_hint_y=None, height=20
        ))
        
        self.brush_size = 1
        self.brush_size_lbl = Label(text="Brush Radius: 1 cell", size_hint_y=None, height=18, font_size='11sp')
        sidebar_layout.add_widget(self.brush_size_lbl)
        self.brush_size_slider = Slider(min=1, max=15, value=1, step=1, size_hint_y=None, height=30)
        def on_brush_size_change(instance, value):
            self.brush_size = int(value)
            self.brush_size_lbl.text = f"Brush Radius: {self.brush_size} cells"
        self.brush_size_slider.bind(value=on_brush_size_change)
        sidebar_layout.add_widget(self.brush_size_slider)
        
        sidebar_layout.add_widget(Label(
            text="[b][color=ffffff]Climate Overrides[/color][/b]",
            markup=True, font_size='13sp', size_hint_y=None, height=20
        ))
        
        # Climate Presets
        climate_presets = [
            ("Ocean", -100.0, 20.0, 0.5),
            ("Coast", -25.0, 20.0, 0.5),
            ("Mountain", 2000.0, 5.0, 0.3),
            ("Tundra", 500.0, 0.0, 0.4),
            ("Desert", 500.0, 30.0, 0.1),
            ("Forest", 500.0, 20.0, 0.7),
            ("Grasslands", 500.0, 20.0, 0.4),
        ]
        
        for name, elev, temp, moist in climate_presets:
            btn = ToggleButton(
                text=name, group="brushes",
                state="down" if name == "Grasslands" else "normal",
                size_hint_y=None, height=28
            )
            btn.bind(on_press=lambda b, n=name, el=elev, t=temp, m=moist: self.select_climate_brush(n, el, t, m))
            sidebar_layout.add_widget(btn)
            
        sidebar_layout.add_widget(Label(
            text="[b][color=ffffff]Chaos Paths[/color][/b]",
            markup=True, font_size='13sp', size_hint_y=None, height=20
        ))
        
        # Chaos Presets
        chaos_presets = ["#Mass", "#Ordo", "#Motus", "#Flux", "#Vita", "#Nexus", "#Anumis", "#Ratio", "#Lux", "#Omen", "#Aura", "#Lex", "None"]
        for name in chaos_presets:
            btn = ToggleButton(
                text=name, group="brushes",
                size_hint_y=None, height=28
            )
            btn.bind(on_press=lambda b, n=name: self.select_chaos_brush(n))
            sidebar_layout.add_widget(btn)
            
        sidebar_layout.add_widget(Label(
            text="[b][color=ffff00]Parameter Tuner[/color][/b]",
            markup=True, font_size='14sp', size_hint_y=None, height=25
        ))
        
        # Sliders Setup
        self.time_scales = [1, 4, 8, 16]
        initial_time_val = self.config_data.get("time_scale_multiplier", 1)
        initial_time_idx = 0
        if initial_time_val in self.time_scales:
            initial_time_idx = self.time_scales.index(initial_time_val)
            
        self.time_lbl = Label(text=f"Time Scale: {initial_time_val}x", size_hint_y=None, height=18, font_size='11sp')
        sidebar_layout.add_widget(self.time_lbl)
        self.time_slider = Slider(min=0, max=3, value=initial_time_idx, step=1, size_hint_y=None, height=30)
        self.time_slider.bind(value=self.on_time_scale_change)
        self.time_slider.bind(on_touch_up=self.on_tuner_release)
        sidebar_layout.add_widget(self.time_slider)
        
        # 2. Fauna Reproduction Slider
        initial_fauna = self.config_data.get("fauna_base_reproduction_rate", 1.0)
        self.fauna_lbl = Label(text=f"Fauna Reprod: {initial_fauna:.2f}", size_hint_y=None, height=18, font_size='11sp')
        sidebar_layout.add_widget(self.fauna_lbl)
        self.fauna_slider = Slider(min=0.1, max=5.0, value=initial_fauna, size_hint_y=None, height=30)
        self.fauna_slider.bind(value=self.on_fauna_change)
        self.fauna_slider.bind(on_touch_up=self.on_tuner_release)
        sidebar_layout.add_widget(self.fauna_slider)
        
        # 3. Mutation Threshold Slider
        initial_mutation = self.config_data.get("mutation_threshold", 90.0)
        self.mutation_lbl = Label(text=f"Mutation Threshold: {initial_mutation:.1f}", size_hint_y=None, height=18, font_size='11sp')
        sidebar_layout.add_widget(self.mutation_lbl)
        self.mutation_slider = Slider(min=0.0, max=100.0, value=initial_mutation, size_hint_y=None, height=30)
        self.mutation_slider.bind(value=self.on_mutation_change)
        self.mutation_slider.bind(on_touch_up=self.on_tuner_release)
        sidebar_layout.add_widget(self.mutation_slider)
        
        # 4. Flora Growth Rate Slider
        initial_flora_growth = self.config_data.get("flora_base_growth_rate", 1.0)
        self.flora_growth_lbl = Label(text=f"Flora Growth: {initial_flora_growth:.2f}", size_hint_y=None, height=18, font_size='11sp')
        sidebar_layout.add_widget(self.flora_growth_lbl)
        self.flora_growth_slider = Slider(min=0.1, max=5.0, value=initial_flora_growth, size_hint_y=None, height=30)
        self.flora_growth_slider.bind(value=self.on_flora_growth_change)
        self.flora_growth_slider.bind(on_touch_up=self.on_tuner_release)
        sidebar_layout.add_widget(self.flora_growth_slider)
        
        # 4. Registries & Pools editing buttons
        sidebar_layout.add_widget(Label(
            text="[b][color=ff8800]Registries & Pools[/color][/b]",
            markup=True, font_size='13sp', size_hint_y=None, height=20
        ))
        
        economy_btn = Button(
            text="Edit Economy Registry",
            size_hint_y=None, height=32,
            background_color=(0.7, 0.4, 0.1, 1.0)
        )
        economy_btn.bind(on_release=self.show_economy_editor)
        sidebar_layout.add_widget(economy_btn)
        
        psych_btn = Button(
            text="Edit Paragon Traits/Goals",
            size_hint_y=None, height=32,
            background_color=(0.7, 0.1, 0.4, 1.0)
        )
        psych_btn.bind(on_release=self.show_psychology_editor)
        sidebar_layout.add_widget(psych_btn)
        
        flora_btn = Button(
            text="Edit Flora Registry",
            size_hint_y=None, height=32,
            background_color=(0.1, 0.6, 0.4, 1.0)
        )
        flora_btn.bind(on_release=self.show_flora_editor)
        sidebar_layout.add_widget(flora_btn)
        
        fauna_btn = Button(
            text="Edit Wildlife Registry",
            size_hint_y=None, height=32,
            background_color=(0.1, 0.4, 0.6, 1.0)
        )
        fauna_btn.bind(on_release=self.show_fauna_editor)
        sidebar_layout.add_widget(fauna_btn)
        
        faction_btn = Button(
            text="Edit Faction Registry",
            size_hint_y=None, height=32,
            background_color=(0.5, 0.3, 0.6, 1.0)
        )
        faction_btn.bind(on_release=self.show_faction_editor)
        sidebar_layout.add_widget(faction_btn)
        
        races_btn = Button(
            text="Edit Races Registry",
            size_hint_y=None, height=32,
            background_color=(0.2, 0.5, 0.5, 1.0)
        )
        races_btn.bind(on_release=self.show_races_editor)
        sidebar_layout.add_widget(races_btn)
        
        exit_btn = Button(
            text="Exit Dashboard",
            size_hint_y=None, height=36,
            background_color=(0.8, 0.2, 0.2, 1.0)
        )
        exit_btn.bind(on_release=lambda b: App.get_running_app().stop())
        sidebar_layout.add_widget(exit_btn)
        
        sidebar_scroll.add_widget(sidebar_layout)
        root_layout.add_widget(sidebar_scroll)
        
        # Start download of map in a background thread
        threading.Thread(target=self.download_crust_mesh, daemon=True).start()
        
        return root_layout

    def _update_sidebar_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
        
    def select_climate_brush(self, name, elev, temp, moist):
        self.active_brush = {
            "type": "climate_override",
            "name": name,
            "elevation": elev,
            "temperature": temp,
            "moisture": moist,
            "chaos_tag": None
        }
        print(f"Selected climate override brush: {name}")
        
    def select_chaos_brush(self, tag):
        self.active_brush = {
            "type": "chaos_path",
            "name": tag,
            "elevation": None,
            "temperature": None,
            "moisture": None,
            "chaos_tag": tag
        }
        print(f"Selected chaos path brush: {tag}")
        
    def on_time_scale_change(self, instance, value):
        idx = int(round(value))
        val = self.time_scales[idx]
        self.time_lbl.text = f"Time Scale: {val}x"
        
    def on_fauna_change(self, instance, value):
        self.fauna_lbl.text = f"Fauna Reprod: {value:.2f}"
        
    def on_mutation_change(self, instance, value):
        self.mutation_lbl.text = f"Mutation Threshold: {value:.1f}"
        
    def on_flora_growth_change(self, instance, value):
        self.flora_growth_lbl.text = f"Flora Growth: {value:.2f}"
        
    def on_tuner_release(self, instance, touch):
        # Trigger config updates to active FastAPI server
        if instance.collide_point(*touch.pos):
            time_idx = int(round(self.time_slider.value))
            time_val = self.time_scales[time_idx]
            config = {
                "time_scale_multiplier": time_val,
                "fauna_base_reproduction_rate": round(self.fauna_slider.value, 2),
                "mutation_threshold": round(self.mutation_slider.value, 1),
                "flora_base_growth_rate": round(self.flora_growth_slider.value, 2)
            }
            # Keep other config blocks intact
            for k in ["economy_and_production_registry", "paragon_psychology_pool"]:
                if k in self.config_data:
                    config[k] = self.config_data[k]
            print(f"APPLY_TEMPLATE config update: {config}")
            self.ws_client.send_config(config)
            
    def on_seed_click(self, instance):
        if self.is_seeding:
            return
        self.is_seeding = True
        self.seed_btn.text = "Generating..."
        self.seed_btn.disabled = True
        threading.Thread(target=self.run_seed_crust_thread, daemon=True).start()
        
    def run_seed_crust_thread(self):
        try:
            r = requests.post(f"{SERVER_URL}/api/builder/generate-crust", timeout=45.0)
            if r.status_code == 200:
                print("Base crust generated successfully on the database.")
                self.download_crust_mesh()
            else:
                print(f"Seeding failed: Status {r.status_code}")
        except Exception as e:
            print(f"Failed to trigger seeding POST: {e}")
        finally:
            def restore_button(dt):
                self.seed_btn.text = "Generate Base Crust"
                self.seed_btn.disabled = False
                self.is_seeding = False
            Clock.schedule_once(restore_button, 0.5)

    def download_crust_mesh(self):
        print(f"Downloading world crust mesh...")
        try:
            r = requests.get(f"{SERVER_URL}/api/builder/crust-mesh", timeout=20.0)
            if r.status_code == 200:
                data = r.json()
                temp_elev = [[0.0 for _ in range(300)] for _ in range(300)]
                temp_temp = [[15.0 for _ in range(300)] for _ in range(300)]
                temp_moist = [[0.5 for _ in range(300)] for _ in range(300)]
                temp_tags = [[None for _ in range(300)] for _ in range(300)]
                
                for cell in data:
                    x = cell["coord_x"]
                    y = cell["coord_y"]
                    if 0 <= x < 300 and 0 <= y < 300:
                        temp_elev[x][y] = cell["elevation_meters"]
                        temp_temp[x][y] = cell["temperature_celsius"]
                        temp_moist[x][y] = cell["moisture_index"]
                        temp_tags[x][y] = cell["active_chaos_tag"]
                        
                with self.data_lock:
                    self.elevation_data[:] = temp_elev
                    self.temperature_data[:] = temp_temp
                    self.moisture_data[:] = temp_moist
                    self.chaos_tags[:] = temp_tags
                    
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self.builder_canvas.update_texture())
                print("Planetary builder grid data cached.")
        except Exception as e:
            print(f"Failed to download builder crust data: {e}")

    def dispatch_paint_stroke(self):
        # Package and dispatch painted cells in a thread
        with self.data_lock:
            cells_to_paint = [PaintCell(x=x, y=y) for x, y in self.drag_buffer]
            self.drag_buffer.clear()
            
        if not cells_to_paint:
            return
            
        payload = {
            "cells": [c.dict() for c in cells_to_paint],
            "brush_name": self.active_brush["name"],
            "elevation": self.active_brush["elevation"],
            "temperature": self.active_brush["temperature"],
            "moisture": self.active_brush["moisture"],
            "chaos_tag": self.active_brush["chaos_tag"]
        }
        
        threading.Thread(target=self.send_paint_stroke_thread, args=(payload,), daemon=True).start()

    def send_paint_stroke_thread(self, payload):
        try:
            r = requests.post(f"{SERVER_URL}/api/builder/paint", json=payload, timeout=10.0)
            if r.status_code == 200:
                print(f"Server synchronized painted stroke.")
                # Force refresh local mesh caches
                self.download_crust_mesh()
            else:
                print(f"Server rejected painted stroke: Status {r.status_code}")
        except Exception as e:
            print(f"Failed to dispatch painted stroke: {e}")

    def show_economy_editor(self, instance):
        current_data = self.config_data.get("economy_and_production_registry", {})
        
        rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        rows_layout.bind(minimum_height=rows_layout.setter('height'))
        
        row_widgets = []
        
        def add_row_widget(name="", tag="", tier="Camp"):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=36, spacing=5)
            
            name_input = TextInput(text=name, multiline=False, size_hint_x=0.3, write_tab=False)
            tag_input = TextInput(text=tag, multiline=False, size_hint_x=0.3, write_tab=False)
            
            from kivy.uix.spinner import Spinner
            tier_spinner = Spinner(
                text=tier,
                values=("Camp", "Hamlet", "Village", "Town", "City", "Metropolis"),
                size_hint_x=0.3
            )
            
            del_btn = Button(text="Delete", size_hint_x=0.1, background_color=(0.7, 0.2, 0.2, 1.0))
            
            row.add_widget(name_input)
            row.add_widget(tag_input)
            row.add_widget(tier_spinner)
            row.add_widget(del_btn)
            
            rows_layout.add_widget(row)
            row_info = {"widget": row, "name_input": name_input, "tag_input": tag_input, "tier_spinner": tier_spinner}
            row_widgets.append(row_info)
            
            def on_delete(b):
                rows_layout.remove_widget(row)
                if row_info in row_widgets:
                    row_widgets.remove(row_info)
            del_btn.bind(on_release=on_delete)

        for k, v in current_data.items():
            add_row_widget(name=k, tag=v.get("requires_tag", ""), tier=v.get("unlocked_at_tier", "Camp"))
            
        if not row_widgets:
            add_row_widget()
            
        scroll_view = ScrollView(size_hint=(1.0, 0.8))
        scroll_view.add_widget(rows_layout)
        
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        headers = BoxLayout(orientation='horizontal', size_hint_y=None, height=20, spacing=5)
        headers.add_widget(Label(text="Commodity Name", size_hint_x=0.3, bold=True, font_size='12sp'))
        headers.add_widget(Label(text="Required Tag", size_hint_x=0.3, bold=True, font_size='12sp'))
        headers.add_widget(Label(text="Unlocked At Tier", size_hint_x=0.3, bold=True, font_size='12sp'))
        headers.add_widget(Label(text="", size_hint_x=0.1))
        
        popup_layout.add_widget(headers)
        popup_layout.add_widget(scroll_view)
        
        add_btn = Button(text="+ Add Commodity", size_hint_y=None, height=36, background_color=(0.2, 0.5, 0.7, 1.0))
        def on_add_press(b):
            add_row_widget()
        add_btn.bind(on_release=on_add_press)
        popup_layout.add_widget(add_btn)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0))
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Economy & Production Registry",
            content=popup_layout,
            size_hint=(0.9, 0.9),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        def save_release(btn):
            new_registry = {}
            for row in row_widgets:
                name = row["name_input"].text.strip()
                tag = row["tag_input"].text.strip()
                tier = row["tier_spinner"].text.strip()
                if name:
                    new_registry[name] = {"requires_tag": tag, "unlocked_at_tier": tier}
            
            self.config_data["economy_and_production_registry"] = new_registry
            self.ws_client.send_config(dict(self.config_data))
            popup.dismiss()
            
        save_btn.bind(on_release=save_release)
        popup.open()
        
    def show_psychology_editor(self, instance):
        current_data = self.config_data.get("paragon_psychology_pool", {})
        first_names = current_data.get("first_names", [])
        last_names = current_data.get("last_names", [])
        positive_traits = current_data.get("positive_traits", [])
        negative_traits = current_data.get("negative_traits", [])
        neutral_traits = current_data.get("neutral_traits", [])
        goals = current_data.get("personal_goals", [])
        
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        columns_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1.0, 0.85))
        
        def create_column(title, items, add_btn_text):
            col_layout = BoxLayout(orientation='vertical', spacing=5)
            col_layout.add_widget(Label(text=title, bold=True, font_size='12sp', size_hint_y=None, height=20))
            
            rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=3)
            rows_layout.bind(minimum_height=rows_layout.setter('height'))
            
            row_inputs = []
            
            def add_item_row(text=""):
                row = BoxLayout(orientation='horizontal', size_hint_y=None, height=32, spacing=2)
                txt = TextInput(text=text, multiline=False, size_hint_x=0.8, write_tab=False)
                del_btn = Button(text="X", size_hint_x=0.2, background_color=(0.7, 0.2, 0.2, 1.0))
                row.add_widget(txt)
                row.add_widget(del_btn)
                rows_layout.add_widget(row)
                row_inputs.append(txt)
                
                def on_del(b):
                    rows_layout.remove_widget(row)
                    if txt in row_inputs:
                        row_inputs.remove(txt)
                del_btn.bind(on_release=on_del)
                
            for item in items:
                add_item_row(item)
                
            if not row_inputs:
                add_item_row()
                
            scroll = ScrollView()
            scroll.add_widget(rows_layout)
            col_layout.add_widget(scroll)
            
            add_btn = Button(text=add_btn_text, size_hint_y=None, height=32, background_color=(0.2, 0.5, 0.7, 1.0))
            def on_add(b):
                add_item_row()
            add_btn.bind(on_release=on_add)
            col_layout.add_widget(add_btn)
            
            return col_layout, row_inputs
        
        col_fn, fn_inputs = create_column("First Names", first_names, "+ Add First")
        col_ln, ln_inputs = create_column("Last Names", last_names, "+ Add Last")
        col_pt, pt_inputs = create_column("Positive", positive_traits, "+ Add Pos")
        col_nt, nt_inputs = create_column("Negative", negative_traits, "+ Add Neg")
        col_neu, neu_inputs = create_column("Neutral", neutral_traits, "+ Add Neu")
        col_g, g_inputs = create_column("Goals", goals, "+ Add Goal")
        
        columns_layout.add_widget(col_fn)
        columns_layout.add_widget(col_ln)
        columns_layout.add_widget(col_pt)
        columns_layout.add_widget(col_nt)
        columns_layout.add_widget(col_neu)
        columns_layout.add_widget(col_g)
        popup_layout.add_widget(columns_layout)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0))
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Paragon Traits & Goals Pool",
            content=popup_layout,
            size_hint=(0.98, 0.98),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        def save_release(btn):
            new_psych = {
                "first_names": [ti.text.strip() for ti in fn_inputs if ti.text.strip()],
                "last_names": [ti.text.strip() for ti in ln_inputs if ti.text.strip()],
                "positive_traits": [ti.text.strip() for ti in pt_inputs if ti.text.strip()],
                "negative_traits": [ti.text.strip() for ti in nt_inputs if ti.text.strip()],
                "neutral_traits": [ti.text.strip() for ti in neu_inputs if ti.text.strip()],
                "personal_goals": [ti.text.strip() for ti in g_inputs if ti.text.strip()]
            }
            self.config_data["paragon_psychology_pool"] = new_psych
            self.ws_client.send_config(dict(self.config_data))
            popup.dismiss()
            
        save_btn.bind(on_release=save_release)
        popup.open()
        
    def show_flora_editor(self, instance):
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        loading_lbl = Label(text="Loading flora registry from server...", font_size='14sp', size_hint=(1.0, 0.9))
        popup_layout.add_widget(loading_lbl)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0), disabled=True)
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Flora (Plants) Registry",
            content=popup_layout,
            size_hint=(0.98, 0.98),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        rows_layout.bind(minimum_height=rows_layout.setter('height'))
        
        row_widgets = []
        
        def add_flora_row(sci_name="", com_name="", t_min=0.0, t_max=0.0, m_min=0.0, m_max=0.0, g_mod=1.0, res="", fatal=False, tags_list=None):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=36, spacing=2)
            
            sci_in = TextInput(text=str(sci_name), multiline=False, size_hint_x=0.15, write_tab=False)
            com_in = TextInput(text=str(com_name), multiline=False, size_hint_x=0.15, write_tab=False)
            t_min_in = TextInput(text=str(t_min), multiline=False, size_hint_x=0.08, write_tab=False)
            t_max_in = TextInput(text=str(t_max), multiline=False, size_hint_x=0.08, write_tab=False)
            m_min_in = TextInput(text=str(m_min), multiline=False, size_hint_x=0.08, write_tab=False)
            m_max_in = TextInput(text=str(m_max), multiline=False, size_hint_x=0.08, write_tab=False)
            g_mod_in = TextInput(text=str(g_mod), multiline=False, size_hint_x=0.08, write_tab=False)
            res_in = TextInput(text=str(res), multiline=False, size_hint_x=0.12, write_tab=False)
            
            # Fatal Toggle
            fatal_btn = Button(text="Fatal" if fatal else "Safe", size_hint_x=0.08, background_color=(0.7, 0.3, 0.1, 1.0) if fatal else (0.1, 0.5, 0.3, 1.0))
            def toggle_fatal(b):
                if b.text == "Fatal":
                    b.text = "Safe"
                    b.background_color = (0.1, 0.5, 0.3, 1.0)
                else:
                    b.text = "Fatal"
                    b.background_color = (0.7, 0.3, 0.1, 1.0)
            fatal_btn.bind(on_release=toggle_fatal)
            
            tags_str = ", ".join(tags_list) if tags_list else ""
            tags_in = TextInput(text=tags_str, multiline=False, size_hint_x=0.12, write_tab=False)
            
            del_btn = Button(text="Delete", size_hint_x=0.08, background_color=(0.7, 0.2, 0.2, 1.0))
            
            row.add_widget(sci_in)
            row.add_widget(com_in)
            row.add_widget(t_min_in)
            row.add_widget(t_max_in)
            row.add_widget(m_min_in)
            row.add_widget(m_max_in)
            row.add_widget(g_mod_in)
            row.add_widget(res_in)
            row.add_widget(fatal_btn)
            row.add_widget(tags_in)
            row.add_widget(del_btn)
            
            rows_layout.add_widget(row)
            row_info = {
                "widget": row,
                "sci_in": sci_in,
                "com_in": com_in,
                "t_min_in": t_min_in,
                "t_max_in": t_max_in,
                "m_min_in": m_min_in,
                "m_max_in": m_max_in,
                "g_mod_in": g_mod_in,
                "res_in": res_in,
                "fatal_btn": fatal_btn,
                "tags_in": tags_in
            }
            row_widgets.append(row_info)
            
            def on_delete(b):
                rows_layout.remove_widget(row)
                if row_info in row_widgets:
                    row_widgets.remove(row_info)
            del_btn.bind(on_release=on_delete)
            
        def on_fetch_success(dt, data):
            popup_layout.clear_widgets()
            
            headers = BoxLayout(orientation='horizontal', size_hint_y=None, height=20, spacing=2)
            headers.add_widget(Label(text="Sci Name", size_hint_x=0.15, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Common Name", size_hint_x=0.15, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="T Min", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="T Max", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="M Min", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="M Max", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Growth Mod", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Harvest Res", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Harvest", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Tags", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="", size_hint_x=0.08))
            
            popup_layout.add_widget(headers)
            
            scroll_view = ScrollView(size_hint=(1.0, 0.75))
            scroll_view.add_widget(rows_layout)
            popup_layout.add_widget(scroll_view)
            
            for item in data:
                add_flora_row(
                    sci_name=item.get("scientific_name", ""),
                    com_name=item.get("common_name", ""),
                    t_min=item.get("temp_preference_min", 0.0),
                    t_max=item.get("temp_preference_max", 0.0),
                    m_min=item.get("moisture_preference_min", 0.0),
                    m_max=item.get("moisture_preference_max", 0.0),
                    g_mod=item.get("growth_rate_modifier", 1.0),
                    res=item.get("harvest_resource", "") or "",
                    fatal=item.get("is_fatal_harvest", False),
                    tags_list=item.get("tags", [])
                )
            
            add_btn = Button(text="+ Add Flora Item", size_hint_y=None, height=36, background_color=(0.2, 0.5, 0.7, 1.0))
            def on_add_press(b):
                add_flora_row()
            add_btn.bind(on_release=on_add_press)
            popup_layout.add_widget(add_btn)
            
            popup_layout.add_widget(btn_layout)
            save_btn.disabled = False
            
        def on_fetch_failed(dt, err_msg):
            loading_lbl.text = f"Failed to fetch flora registry: {err_msg}"
            
        def fetch_thread():
            try:
                r = requests.get(f"{SERVER_URL}/api/registry/flora", timeout=5.0)
                if r.status_code == 200:
                    Clock.schedule_once(lambda dt: on_fetch_success(dt, r.json()))
                else:
                    Clock.schedule_once(lambda dt: on_fetch_failed(dt, f"Status {r.status_code}"))
            except Exception as e:
                err_msg = str(e)
                Clock.schedule_once(lambda dt, msg=err_msg: on_fetch_failed(dt, msg))
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
        def save_release(btn):
            save_btn.disabled = True
            save_btn.text = "Syncing..."
            
            payload = []
            for row in row_widgets:
                sci = row["sci_in"].text.strip()
                com = row["com_in"].text.strip()
                if not sci:
                    continue
                try:
                    tags_p = [t.strip() for t in row["tags_in"].text.split(",") if t.strip()]
                    payload.append({
                        "scientific_name": sci,
                        "common_name": com,
                        "temp_preference_min": float(row["t_min_in"].text or 0.0),
                        "temp_preference_max": float(row["t_max_in"].text or 0.0),
                        "moisture_preference_min": float(row["m_min_in"].text or 0.0),
                        "moisture_preference_max": float(row["m_max_in"].text or 0.0),
                        "growth_rate_modifier": float(row["g_mod_in"].text or 1.0),
                        "harvest_resource": row["res_in"].text.strip() or None,
                        "is_fatal_harvest": row["fatal_btn"].text == "Fatal",
                        "tags": tags_p
                    })
                except ValueError:
                    popup.title = "ValueError: Ensure numeric fields are numbers!"
                    save_btn.disabled = False
                    save_btn.text = "Save & Sync"
                    return
            
            def save_thread():
                try:
                    r = requests.post(f"{SERVER_URL}/api/registry/flora", json=payload, timeout=10.0)
                    if r.status_code == 200:
                        Clock.schedule_once(lambda dt: popup.dismiss())
                    else:
                        def handle_err(dt):
                            popup.title = f"Sync Failed: Status {r.status_code}"
                            save_btn.disabled = False
                            save_btn.text = "Save & Sync"
                        Clock.schedule_once(handle_err)
                except Exception as e:
                    err_msg = str(e)
                    def handle_err(dt, msg=err_msg):
                        popup.title = f"Sync Error: {msg}"
                        save_btn.disabled = False
                        save_btn.text = "Save & Sync"
                    Clock.schedule_once(handle_err)
            
            threading.Thread(target=save_thread, daemon=True).start()
            
        save_btn.bind(on_release=save_release)
        popup.open()
 
    def show_fauna_editor(self, instance):
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        loading_lbl = Label(text="Loading wildlife registry from server...", font_size='14sp', size_hint=(1.0, 0.9))
        popup_layout.add_widget(loading_lbl)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0), disabled=True)
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Wildlife (Fauna) Registry",
            content=popup_layout,
            size_hint=(0.98, 0.98),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        rows_layout.bind(minimum_height=rows_layout.setter('height'))
        
        row_widgets = []
        
        def add_fauna_row(sci_name="", com_name="", diet="Herbivore", pack=1, reprod=1.0, res="", fatal=True, tags_list=None):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=36, spacing=2)
            
            sci_in = TextInput(text=str(sci_name), multiline=False, size_hint_x=0.18, write_tab=False)
            com_in = TextInput(text=str(com_name), multiline=False, size_hint_x=0.18, write_tab=False)
            diet_in = TextInput(text=str(diet), multiline=False, size_hint_x=0.12, write_tab=False)
            pack_in = TextInput(text=str(pack), multiline=False, size_hint_x=0.08, write_tab=False)
            reprod_in = TextInput(text=str(reprod), multiline=False, size_hint_x=0.08, write_tab=False)
            res_in = TextInput(text=str(res), multiline=False, size_hint_x=0.12, write_tab=False)
            
            fatal_btn = Button(text="Fatal" if fatal else "Safe", size_hint_x=0.08, background_color=(0.7, 0.3, 0.1, 1.0) if fatal else (0.1, 0.5, 0.3, 1.0))
            def toggle_fatal(b):
                if b.text == "Fatal":
                    b.text = "Safe"
                    b.background_color = (0.1, 0.5, 0.3, 1.0)
                else:
                    b.text = "Fatal"
                    b.background_color = (0.7, 0.3, 0.1, 1.0)
            fatal_btn.bind(on_release=toggle_fatal)
            
            tags_str = ", ".join(tags_list) if tags_list else ""
            tags_in = TextInput(text=tags_str, multiline=False, size_hint_x=0.12, write_tab=False)
            
            del_btn = Button(text="Delete", size_hint_x=0.08, background_color=(0.7, 0.2, 0.2, 1.0))
            
            row.add_widget(sci_in)
            row.add_widget(com_in)
            row.add_widget(diet_in)
            row.add_widget(pack_in)
            row.add_widget(reprod_in)
            row.add_widget(res_in)
            row.add_widget(fatal_btn)
            row.add_widget(tags_in)
            row.add_widget(del_btn)
            
            rows_layout.add_widget(row)
            row_info = {
                "widget": row,
                "sci_in": sci_in,
                "com_in": com_in,
                "diet_in": diet_in,
                "pack_in": pack_in,
                "reprod_in": reprod_in,
                "res_in": res_in,
                "fatal_btn": fatal_btn,
                "tags_in": tags_in
            }
            row_widgets.append(row_info)
            
            def on_delete(b):
                rows_layout.remove_widget(row)
                if row_info in row_widgets:
                    row_widgets.remove(row_info)
            del_btn.bind(on_release=on_delete)
            
        def on_fetch_success(dt, data):
            popup_layout.clear_widgets()
            
            headers = BoxLayout(orientation='horizontal', size_hint_y=None, height=20, spacing=2)
            headers.add_widget(Label(text="Sci Name", size_hint_x=0.18, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Common Name", size_hint_x=0.18, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Diet", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Pack Size", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Reprod Rate", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Harvest Res", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Harvest", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Tags", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="", size_hint_x=0.08))
            
            popup_layout.add_widget(headers)
            
            scroll_view = ScrollView(size_hint=(1.0, 0.75))
            scroll_view.add_widget(rows_layout)
            popup_layout.add_widget(scroll_view)
            
            for item in data:
                add_fauna_row(
                    sci_name=item.get("scientific_name", ""),
                    com_name=item.get("common_name", ""),
                    diet=item.get("dietary_classification", "Herbivore"),
                    pack=item.get("base_pack_size", 1),
                    reprod=item.get("reproduction_rate", 1.0),
                    res=item.get("harvest_resource", "") or "",
                    fatal=item.get("is_fatal_harvest", True),
                    tags_list=item.get("tags", [])
                )
            
            add_btn = Button(text="+ Add Wildlife Item", size_hint_y=None, height=36, background_color=(0.2, 0.5, 0.7, 1.0))
            def on_add_press(b):
                add_fauna_row()
            add_btn.bind(on_release=on_add_press)
            popup_layout.add_widget(add_btn)
            
            popup_layout.add_widget(btn_layout)
            save_btn.disabled = False
            
        def on_fetch_failed(dt, err_msg):
            loading_lbl.text = f"Failed to fetch wildlife registry: {err_msg}"
            
        def fetch_thread():
            try:
                r = requests.get(f"{SERVER_URL}/api/registry/fauna", timeout=5.0)
                if r.status_code == 200:
                    Clock.schedule_once(lambda dt: on_fetch_success(dt, r.json()))
                else:
                    Clock.schedule_once(lambda dt: on_fetch_failed(dt, f"Status {r.status_code}"))
            except Exception as e:
                err_msg = str(e)
                Clock.schedule_once(lambda dt, msg=err_msg: on_fetch_failed(dt, msg))
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
        def save_release(btn):
            save_btn.disabled = True
            save_btn.text = "Syncing..."
            
            payload = []
            for row in row_widgets:
                sci = row["sci_in"].text.strip()
                com = row["com_in"].text.strip()
                diet = row["diet_in"].text.strip()
                if not sci:
                    continue
                try:
                    tags_p = [t.strip() for t in row["tags_in"].text.split(",") if t.strip()]
                    payload.append({
                        "scientific_name": sci,
                        "common_name": com,
                        "dietary_classification": diet,
                        "base_pack_size": int(row["pack_in"].text or 1),
                        "reproduction_rate": float(row["reprod_in"].text or 1.0),
                        "harvest_resource": row["res_in"].text.strip() or None,
                        "is_fatal_harvest": row["fatal_btn"].text == "Fatal",
                        "tags": tags_p
                    })
                except ValueError:
                    popup.title = "ValueError: Ensure Pack Size is int and Reprod Rate is float!"
                    save_btn.disabled = False
                    save_btn.text = "Save & Sync"
                    return
            
            def save_thread():
                try:
                    r = requests.post(f"{SERVER_URL}/api/registry/fauna", json=payload, timeout=10.0)
                    if r.status_code == 200:
                        Clock.schedule_once(lambda dt: popup.dismiss())
                    else:
                        def handle_err(dt):
                            popup.title = f"Sync Failed: Status {r.status_code}"
                            save_btn.disabled = False
                            save_btn.text = "Save & Sync"
                        Clock.schedule_once(handle_err)
                except Exception as e:
                    err_msg = str(e)
                    def handle_err(dt, msg=err_msg):
                        popup.title = f"Sync Error: {msg}"
                        save_btn.disabled = False
                        save_btn.text = "Save & Sync"
                    Clock.schedule_once(handle_err)
            
            threading.Thread(target=save_thread, daemon=True).start()
            
        save_btn.bind(on_release=save_release)
        popup.open()
 
    def show_faction_editor(self, instance):
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        loading_lbl = Label(text="Loading faction registry from server...", font_size='14sp', size_hint=(1.0, 0.9))
        popup_layout.add_widget(loading_lbl)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0), disabled=True)
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Factions Registry",
            content=popup_layout,
            size_hint=(0.98, 0.98),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        rows_layout.bind(minimum_height=rows_layout.setter('height'))
        
        row_widgets = []
        
        def add_faction_row(fac_name="", ideology="", rep=0, f_type="goverments", exp=5, agg=5, trd=5, gov="republic", tags_list=None, trait="bonus_trade"):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=36, spacing=2)
            
            fac_in = TextInput(text=str(fac_name), multiline=False, size_hint_x=0.15, write_tab=False)
            ideology_in = TextInput(text=str(ideology), multiline=False, size_hint_x=0.12, write_tab=False)
            rep_in = TextInput(text=str(rep), multiline=False, size_hint_x=0.07, write_tab=False)
            
            from kivy.uix.spinner import Spinner
            type_spinner = Spinner(
                text=str(f_type),
                values=("goverments", "cartels", "zealots/religious groups", "ideological orders", "mercenary groups", "pirates"),
                size_hint_x=0.12
            )
            
            exp_in = TextInput(text=str(exp), multiline=False, size_hint_x=0.06, write_tab=False)
            agg_in = TextInput(text=str(agg), multiline=False, size_hint_x=0.06, write_tab=False)
            trd_in = TextInput(text=str(trd), multiline=False, size_hint_x=0.06, write_tab=False)
            
            gov_spinner = Spinner(
                text=str(gov),
                values=("monarchy", "republic", "capitalist", "communist", "commonwealth", "confederacy", "free states", "religious", "dictatorship", "horde/hive", "tribal", "feudalism", "anarchy"),
                size_hint_x=0.12
            )
            
            tags_str = ", ".join(tags_list) if tags_list else ""
            tags_in = TextInput(text=tags_str, multiline=False, size_hint_x=0.10, write_tab=False)
            
            trait_spinner = Spinner(
                text=str(trait),
                values=("bonus_trade", "tougher_security", "higher_growth", "bonus_production", "lower_transit_risk", "slower_food_consumption"),
                size_hint_x=0.12
            )
            
            del_btn = Button(text="Delete", size_hint_x=0.06, background_color=(0.7, 0.2, 0.2, 1.0))
            
            row.add_widget(fac_in)
            row.add_widget(ideology_in)
            row.add_widget(rep_in)
            row.add_widget(type_spinner)
            row.add_widget(exp_in)
            row.add_widget(agg_in)
            row.add_widget(trd_in)
            row.add_widget(gov_spinner)
            row.add_widget(tags_in)
            row.add_widget(trait_spinner)
            row.add_widget(del_btn)
            
            rows_layout.add_widget(row)
            row_info = {
                "widget": row,
                "fac_in": fac_in,
                "ideology_in": ideology_in,
                "rep_in": rep_in,
                "type_spinner": type_spinner,
                "exp_in": exp_in,
                "agg_in": agg_in,
                "trd_in": trd_in,
                "gov_spinner": gov_spinner,
                "tags_in": tags_in,
                "trait_spinner": trait_spinner
            }
            row_widgets.append(row_info)
            
            def on_delete(b):
                rows_layout.remove_widget(row)
                if row_info in row_widgets:
                    row_widgets.remove(row_info)
            del_btn.bind(on_release=on_delete)
            
        def on_fetch_success(dt, data):
            popup_layout.clear_widgets()
            
            headers = BoxLayout(orientation='horizontal', size_hint_y=None, height=20, spacing=2)
            headers.add_widget(Label(text="Faction Name", size_hint_x=0.15, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Ideology", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Reputation", size_hint_x=0.07, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Type", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Exp", size_hint_x=0.06, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Agg", size_hint_x=0.06, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Trd", size_hint_x=0.06, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Government", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Tags", size_hint_x=0.10, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Trait", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="", size_hint_x=0.06))
            
            popup_layout.add_widget(headers)
            
            scroll_view = ScrollView(size_hint=(1.0, 0.75))
            scroll_view.add_widget(rows_layout)
            popup_layout.add_widget(scroll_view)
            
            for item in data:
                add_faction_row(
                    fac_name=item.get("faction_name", ""),
                    ideology=item.get("ideology_type", ""),
                    rep=item.get("reputation_baseline", 0),
                    f_type=item.get("faction_type", "goverments"),
                    exp=item.get("expansion_level", 5),
                    agg=item.get("aggression_level", 5),
                    trd=item.get("trade_level", 5),
                    gov=item.get("government_type", "republic"),
                    tags_list=item.get("tags", []),
                    trait=item.get("faction_trait", "bonus_trade")
                )
            
            add_btn = Button(text="+ Add Faction Item", size_hint_y=None, height=36, background_color=(0.2, 0.5, 0.7, 1.0))
            def on_add_press(b):
                add_faction_row()
            add_btn.bind(on_release=on_add_press)
            popup_layout.add_widget(add_btn)
            
            popup_layout.add_widget(btn_layout)
            save_btn.disabled = False
            
        def on_fetch_failed(dt, err_msg):
            loading_lbl.text = f"Failed to fetch factions registry: {err_msg}"
            
        def fetch_thread():
            try:
                r = requests.get(f"{SERVER_URL}/api/registry/factions", timeout=5.0)
                if r.status_code == 200:
                    Clock.schedule_once(lambda dt: on_fetch_success(dt, r.json()))
                else:
                    Clock.schedule_once(lambda dt: on_fetch_failed(dt, f"Status {r.status_code}"))
            except Exception as e:
                err_msg = str(e)
                Clock.schedule_once(lambda dt, msg=err_msg: on_fetch_failed(dt, msg))
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
        def save_release(btn):
            save_btn.disabled = True
            save_btn.text = "Syncing..."
            
            payload = []
            for row in row_widgets:
                name = row["fac_in"].text.strip()
                ideology = row["ideology_in"].text.strip()
                if not name:
                    continue
                try:
                    tags_p = [t.strip() for t in row["tags_in"].text.split(",") if t.strip()]
                    payload.append({
                        "faction_name": name,
                        "ideology_type": ideology,
                        "reputation_baseline": int(row["rep_in"].text or 0),
                        "faction_type": row["type_spinner"].text,
                        "expansion_level": int(row["exp_in"].text or 5),
                        "aggression_level": int(row["agg_in"].text or 5),
                        "trade_level": int(row["trd_in"].text or 5),
                        "government_type": row["gov_spinner"].text,
                        "tags": tags_p,
                        "faction_trait": row["trait_spinner"].text
                    })
                except ValueError:
                    popup.title = "ValueError: Ensure levels and Reputation are integers!"
                    save_btn.disabled = False
                    save_btn.text = "Save & Sync"
                    return
            
            def save_thread():
                try:
                    r = requests.post(f"{SERVER_URL}/api/registry/factions", json=payload, timeout=10.0)
                    if r.status_code == 200:
                        Clock.schedule_once(lambda dt: popup.dismiss())
                    else:
                        def handle_err(dt):
                            popup.title = f"Sync Failed: Status {r.status_code}"
                            save_btn.disabled = False
                            save_btn.text = "Save & Sync"
                        Clock.schedule_once(handle_err)
                except Exception as e:
                    err_msg = str(e)
                    def handle_err(dt, msg=err_msg):
                        popup.title = f"Sync Error: {msg}"
                        save_btn.disabled = False
                        save_btn.text = "Save & Sync"
                    Clock.schedule_once(handle_err)
            
            threading.Thread(target=save_thread, daemon=True).start()
            
        save_btn.bind(on_release=save_release)
        popup.open()

    def show_races_editor(self, instance):
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        loading_lbl = Label(text="Loading sentient species registry from server...", font_size='14sp', size_hint=(1.0, 0.9))
        popup_layout.add_widget(loading_lbl)
        
        btn_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        save_btn = Button(text="Save & Sync", background_color=(0.1, 0.7, 0.4, 1.0), disabled=True)
        cancel_btn = Button(text="Cancel", background_color=(0.7, 0.2, 0.2, 1.0))
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        popup_layout.add_widget(btn_layout)
        
        popup = Popup(
            title="Edit Sentient Species (Races) Registry",
            content=popup_layout,
            size_hint=(0.98, 0.98),
            auto_dismiss=False
        )
        
        cancel_btn.bind(on_release=popup.dismiss)
        
        rows_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        rows_layout.bind(minimum_height=rows_layout.setter('height'))
        
        row_widgets = []
        
        def add_race_row(race_name="", genus="mammal", faction="", t_min=-10.0, t_max=30.0, m_min=0.2, m_max=0.8, reprod=1.0, food=1.0):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=36, spacing=2)
            
            race_in = TextInput(text=str(race_name), multiline=False, size_hint_x=0.18, write_tab=False)
            
            from kivy.uix.spinner import Spinner
            genus_spinner = Spinner(
                text=str(genus),
                values=("plant", "insect", "mammal", "avian", "reptile", "aquatic"),
                size_hint_x=0.12
            )
            
            fac_in = TextInput(text=str(faction or ""), multiline=False, size_hint_x=0.15, write_tab=False)
            t_min_in = TextInput(text=str(t_min), multiline=False, size_hint_x=0.08, write_tab=False)
            t_max_in = TextInput(text=str(t_max), multiline=False, size_hint_x=0.08, write_tab=False)
            m_min_in = TextInput(text=str(m_min), multiline=False, size_hint_x=0.08, write_tab=False)
            m_max_in = TextInput(text=str(m_max), multiline=False, size_hint_x=0.08, write_tab=False)
            reprod_in = TextInput(text=str(reprod), multiline=False, size_hint_x=0.08, write_tab=False)
            food_in = TextInput(text=str(food), multiline=False, size_hint_x=0.08, write_tab=False)
            
            del_btn = Button(text="Delete", size_hint_x=0.07, background_color=(0.7, 0.2, 0.2, 1.0))
            
            row.add_widget(race_in)
            row.add_widget(genus_spinner)
            row.add_widget(fac_in)
            row.add_widget(t_min_in)
            row.add_widget(t_max_in)
            row.add_widget(m_min_in)
            row.add_widget(m_max_in)
            row.add_widget(reprod_in)
            row.add_widget(food_in)
            row.add_widget(del_btn)
            
            rows_layout.add_widget(row)
            row_info = {
                "widget": row,
                "race_in": race_in,
                "genus_spinner": genus_spinner,
                "fac_in": fac_in,
                "t_min_in": t_min_in,
                "t_max_in": t_max_in,
                "m_min_in": m_min_in,
                "m_max_in": m_max_in,
                "reprod_in": reprod_in,
                "food_in": food_in
            }
            row_widgets.append(row_info)
            
            def on_delete(b):
                rows_layout.remove_widget(row)
                if row_info in row_widgets:
                    row_widgets.remove(row_info)
            del_btn.bind(on_release=on_delete)
            
        def on_fetch_success(dt, data):
            popup_layout.clear_widgets()
            
            headers = BoxLayout(orientation='horizontal', size_hint_y=None, height=20, spacing=2)
            headers.add_widget(Label(text="Race Name", size_hint_x=0.18, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Genus Type", size_hint_x=0.12, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Associated Faction", size_hint_x=0.15, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="T Min", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="T Max", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="M Min", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="M Max", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Reprod Rate", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="Food Cons", size_hint_x=0.08, bold=True, font_size='11sp'))
            headers.add_widget(Label(text="", size_hint_x=0.07))
            
            popup_layout.add_widget(headers)
            
            scroll_view = ScrollView(size_hint=(1.0, 0.75))
            scroll_view.add_widget(rows_layout)
            popup_layout.add_widget(scroll_view)
            
            for item in data:
                add_race_row(
                    race_name=item.get("race_name", ""),
                    genus=item.get("genus_type", "mammal"),
                    faction=item.get("associated_faction_name", "") or "",
                    t_min=item.get("temp_preference_min", -10.0),
                    t_max=item.get("temp_preference_max", 30.0),
                    m_min=item.get("moisture_preference_min", 0.2),
                    m_max=item.get("moisture_preference_max", 0.8),
                    reprod=item.get("reproduction_rate", 1.0),
                    food=item.get("food_consumption_rate", 1.0)
                )
            
            add_btn = Button(text="+ Add Race Item", size_hint_y=None, height=36, background_color=(0.2, 0.5, 0.7, 1.0))
            def on_add_press(b):
                add_race_row()
            add_btn.bind(on_release=on_add_press)
            popup_layout.add_widget(add_btn)
            
            popup_layout.add_widget(btn_layout)
            save_btn.disabled = False
            
        def on_fetch_failed(dt, err_msg):
            loading_lbl.text = f"Failed to fetch sentient races registry: {err_msg}"
            
        def fetch_thread():
            try:
                r = requests.get(f"{SERVER_URL}/api/registry/races", timeout=5.0)
                if r.status_code == 200:
                    Clock.schedule_once(lambda dt: on_fetch_success(dt, r.json()))
                else:
                    Clock.schedule_once(lambda dt: on_fetch_failed(dt, f"Status {r.status_code}"))
            except Exception as e:
                err_msg = str(e)
                Clock.schedule_once(lambda dt, msg=err_msg: on_fetch_failed(dt, msg))
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
        def save_release(btn):
            save_btn.disabled = True
            save_btn.text = "Syncing..."
            
            payload = []
            for row in row_widgets:
                name = row["race_in"].text.strip()
                genus = row["genus_spinner"].text
                fac = row["fac_in"].text.strip()
                if not name:
                    continue
                try:
                    payload.append({
                        "race_name": name,
                        "genus_type": genus,
                        "associated_faction_name": fac if fac else None,
                        "temp_preference_min": float(row["t_min_in"].text or 0.0),
                        "temp_preference_max": float(row["t_max_in"].text or 0.0),
                        "moisture_preference_min": float(row["m_min_in"].text or 0.0),
                        "moisture_preference_max": float(row["m_max_in"].text or 0.0),
                        "reproduction_rate": float(row["reprod_in"].text or 1.0),
                        "food_consumption_rate": float(row["food_in"].text or 1.0)
                    })
                except ValueError:
                    popup.title = "ValueError: Ensure numeric preferences and rates are floats!"
                    save_btn.disabled = False
                    save_btn.text = "Save & Sync"
                    return
            
            def save_thread():
                try:
                    r = requests.post(f"{SERVER_URL}/api/registry/races", json=payload, timeout=10.0)
                    if r.status_code == 200:
                        Clock.schedule_once(lambda dt: popup.dismiss())
                    else:
                        def handle_err(dt):
                            popup.title = f"Sync Failed: Status {r.status_code}"
                            save_btn.disabled = False
                            save_btn.text = "Save & Sync"
                        Clock.schedule_once(handle_err)
                except Exception as e:
                    err_msg = str(e)
                    def handle_err(dt, msg=err_msg):
                        popup.title = f"Sync Error: {msg}"
                        save_btn.disabled = False
                        save_btn.text = "Save & Sync"
                    Clock.schedule_once(handle_err)
            
            threading.Thread(target=save_thread, daemon=True).start()
            
        save_btn.bind(on_release=save_release)
        popup.open()
# Helper models for Pydantic serialization
class PaintCell:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def dict(self):
        return {"x": self.x, "y": self.y}


if __name__ == "__main__":
    # If launched with admin flag, run Builder dashboard
    if len(sys.argv) > 1 and sys.argv[1] == "--admin-editor":
        PlanetaryBuilderDashboardApp().run()
    else:
        SimulationClientApp().run()
