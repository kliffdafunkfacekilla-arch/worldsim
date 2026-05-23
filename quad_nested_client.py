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
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock
from kivy.core.window import Window

# Server API URL
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

class NestedPlanetaryCoordinateEngine:
    """
    Handles movement on a nested planetary grid using 4 nested tiers:
    - Continental: Cx, Cy >= 0 (capped at 0 on underflow)
    - Regional: Rx, Ry in [0, 29]
    - Screen: Sx, Sy in [0, 99]
    - Tile: Tx, Ty in [0, 99]
    
    Total grid coordinates mapped to the 300x300 planetary grid:
    px = (Cx * 30 + Rx) % 300
    py = (Cy * 30 + Ry) % 300
    """
    def __init__(self, cx=3, cy=3, rx=10, ry=10, sx=50, sy=50, tx=10, ty=10):
        self.Cx = cx
        self.Cy = cy
        self.Rx = rx
        self.Ry = ry
        self.Sx = sx
        self.Sy = sy
        self.Tx = tx
        self.Ty = ty
 
    def get_planetary_coords(self):
        px = (self.Cx * 30 + self.Rx) % 300
        py = (self.Cy * 30 + self.Ry) % 300
        return px, py

    def update_player_movement(self, dx, dy, trigger_handshake_callback=None):
        """
        Applies player movement to Tile coords and cascades overflows/underflows up the tiers.
        If a Screen coordinate overflows/underflows (changes parent region), triggers handshake.
        Handles negative movement/underflows correctly.
        """
        tx = self.Tx + dx
        ty = self.Ty + dy
        
        sx, sy = self.Sx, self.Sy
        rx, ry = self.Rx, self.Ry
        cx, cy = self.Cx, self.Cy
        
        screen_changed = False
        
        # --- Cascade X Axis ---
        # Tile X boundaries [0, 99]
        if tx > 99:
            tx = 0
            sx += 1
        elif tx < 0:
            tx = 99
            sx -= 1
            
        # Screen X boundaries [0, 99]
        if sx > 99:
            sx = 0
            rx += 1
            screen_changed = True
        elif sx < 0:
            sx = 99
            rx -= 1
            screen_changed = True
            
        # Regional X boundaries [0, 29]
        if rx > 29:
            rx = 0
            cx += 1
        elif rx < 0:
            rx = 29
            cx -= 1
            
        # --- Cascade Y Axis ---
        # Tile Y boundaries [0, 99]
        if ty > 99:
            ty = 0
            sy += 1
        elif ty < 0:
            ty = 99
            sy -= 1
            
        # Screen Y boundaries [0, 99]
        if sy > 99:
            sy = 0
            ry += 1
            screen_changed = True
        elif sy < 0:
            sy = 99
            ry -= 1
            screen_changed = True
            
        # Regional Y boundaries [0, 29]
        if ry > 29:
            ry = 0
            cy += 1
        elif ry < 0:
            ry = 29
            cy -= 1
            
        # Enforce Continental boundaries (Cx, Cy >= 0)
        if cx < 0:
            cx = 0
        if cy < 0:
            cy = 0
            
        # Update state
        self.Tx = tx
        self.Ty = ty
        self.Sx = sx
        self.Sy = sy
        self.Rx = rx
        self.Ry = ry
        self.Cx = cx
        self.Cy = cy
        
        # Trigger handshake if screen transition occurred
        if screen_changed and trigger_handshake_callback:
            trigger_handshake_callback()
            
        return True


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
        self.elevation_data = elevation_data
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        
        w, h = self.size
        px, py = self.coord_engine.get_planetary_coords()
        tile_x = self.coord_engine.Tx
        tile_y = self.coord_engine.Ty
        
        tile_w = w / 15.0
        tile_h = h / 11.0
        
        with self.canvas:
            for col in range(-1, 16):
                for row in range(-1, 12):
                    cx = px + (col - 7)
                    cy = py + (row - 5)
                    
                    if 0 <= cx < 300 and 0 <= cy < 300:
                        cell_id = cy * 300 + cx + 1
                        
                        active_tag = None
                        with self.data_lock:
                            if cell_id in self.shared_data["cache"]:
                                active_tag = self.shared_data["cache"][cell_id].get("active_chaos_tag")
                        
                        if active_tag and "#Epicenter" in active_tag:
                            Color(0.7, 0.1, 0.1, 1.0)
                        elif active_tag and "#Flux" in active_tag:
                            Color(0.0, 0.8, 0.8, 1.0)
                        elif active_tag and "#Vita" in active_tag:
                            Color(0.1, 0.9, 0.1, 1.0)
                        else:
                            elev = 500.0
                            if self.elevation_data:
                                try:
                                    elev = self.elevation_data[cx][cy]
                                except IndexError:
                                    pass
                            
                            if elev < 0.0:
                                Color(0.1, 0.3, 0.8, 1.0)
                            elif elev > 2000.0:
                                Color(0.5, 0.5, 0.5, 1.0)
                            else:
                                Color(0.15, 0.55, 0.15, 1.0)
                    else:
                        Color(0.05, 0.05, 0.08, 1.0)
                        
                    # Using 100 tiles per screen for scrolling offset
                    x_pos = self.x + (col - (tile_x / 100.0)) * tile_w
                    y_pos = self.y + (row - (tile_y / 100.0)) * tile_h
                    
                    Rectangle(pos=(x_pos + 1, y_pos + 1), size=(tile_w - 2, tile_h - 2))
            
            gold_x = self.x + 7.5 * tile_w
            gold_y = self.y + 5.5 * tile_h
            
            Color(1.0, 0.84, 0.0, 1.0)
            Rectangle(pos=(gold_x - tile_w * 0.15, gold_y - tile_h * 0.15), size=(tile_w * 0.3, tile_h * 0.3))
            Color(1.0, 1.0, 1.0, 1.0)
            Rectangle(pos=(gold_x - tile_w * 0.05, gold_y - tile_h * 0.05), size=(tile_w * 0.1, tile_h * 0.1))


class HUDPanel(BoxLayout):
    """
    Right panel BoxLayout HUD containing dynamic text labels for clocks, coordinates,
    environmental metrics, and character stats.
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
        
        # UI Labels
        self.add_widget(Label(
            text="[b][color=ffaa00]QUAD NESTED HUD[/color][/b]",
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
            text="4-Tier Coordinate Hierarchy:\nCont: (-,-) | Reg: (-,-)\nScr: (-,-) | Tile: (-,-)",
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
        
        # Trigger Damage Button
        self.damage_btn = Button(
            text="Trigger Hazard (Damage)",
            size_hint_y=None,
            height=35,
            background_color=(0.8, 0.2, 0.2, 1.0)
        )
        self.damage_btn.bind(on_release=self.on_damage_click)
        self.add_widget(self.damage_btn)
        
        # Fill rest space
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
        tx = self.coord_engine.Tx
        ty = self.coord_engine.Ty
        sx = self.coord_engine.Sx
        sy = self.coord_engine.Sy
        rx = self.coord_engine.Rx
        ry = self.coord_engine.Ry
        cx = self.coord_engine.Cx
        cy = self.coord_engine.Cy
        
        self.position_label.text = (
            f"Position:\n"
            f"[color=ffffff]Planetary Coords:[/color] [color=ffff00]({px}, {py})[/color]\n"
            f"[color=ffffff]Local Tile:[/color] [color=ffff00]({tx}, {ty})[/color]"
        )
        
        self.hierarchy_label.text = (
            f"4-Tier Coordinate Hierarchy:\n"
            f"[color=aaaaaa]Cont:[/color] ({cx}, {cy}) | "
            f"[color=aaaaaa]Reg:[/color] ({rx}, {ry})\n"
            f"[color=aaaaaa]Scr:[/color] ({sx}, {sy}) | "
            f"[color=aaaaaa]Tile:[/color] ({tx}, {ty})"
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
    Main Kivy desktop client application using variable-tier nested coordinates engine.
    Sets up UI layouts, binds W,A,S,D controls, and runs background heartbeat updates.
    """
    def build(self):
        self.title = "Planetary Simulation quad client"
        
        # Player attributes & pools initialization
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
        self.coord_engine = NestedPlanetaryCoordinateEngine(cx=3, cy=3, rx=10, ry=10, sx=50, sy=50, tx=10, ty=10)
        
        # Thread safety lock and localized memory dictionary
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

    def trigger_server_api_handshake(self):
        """
        Asynchronously triggers a server API call to pull the new simulation block.
        """
        print("API Handshake: Crossing region bounds. Querying simulation block...")
        threading.Thread(target=self.fetch_server_state_thread, daemon=True).start()

    def trigger_hazard_damage(self):
        """
        Locks the new damaged Health state into PostgreSQL immediately.
        """
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
                for cell in data:
                    cx = cell["coord_x"]
                    cy = cell["coord_y"]
                    elev = cell["elevation_meters"]
                    if 0 <= cx < 300 and 0 <= cy < 300:
                        temp_elev[cx][cy] = elev
                
                with self.data_lock:
                    self.elevation_data[:] = temp_elev
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
            
            # Fetch System clock
            r_clock = requests.get(f"{SERVER_URL}/api/world-state", timeout=2.0)
            clock_data = r_clock.json() if r_clock.status_code == 200 else None
            
            # Fetch Chaos resonance context
            r_chaos = requests.get(f"{SERVER_URL}/api/cell/{cell_id}/chaos-context", timeout=2.0)
            chaos_data = r_chaos.json() if r_chaos.status_code == 200 else None
            
            # Fetch Shadow war subversion metrics
            r_shadow = requests.get(f"{SERVER_URL}/api/cell/{cell_id}/shadow-intel", timeout=2.0)
            shadow_data = r_shadow.json() if r_shadow.status_code == 200 else None
            
            # Fetch full cell detail
            r_cell = requests.get(f"{SERVER_URL}/api/cell/{cell_id}", timeout=2.0)
            cell_detail = r_cell.json() if r_cell.status_code == 200 else None
            
            # Fetch Player Character state
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
            # Enforce exact variable-tier nested boundary limits and trigger callback asynchronously on Screen change
            moved = self.coord_engine.update_player_movement(
                dx, dy,
                trigger_handshake_callback=self.trigger_server_api_handshake
            )
            if moved:
                self.canvas_widget.redraw()
                self.hud_widget.update_hud()
        return True

    def update_ui(self, dt):
        self.canvas_widget.redraw()
        self.hud_widget.update_hud()


if __name__ == '__main__':
    SimulationClientApp().run()
