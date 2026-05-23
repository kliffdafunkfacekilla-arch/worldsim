import os
import json
import base64
import io
import requests
import threading
from datetime import datetime
from PIL import Image

# Kivy Framework Imports for UI
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.slider import Slider
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock

# Configuration Targets matching Phase 1/2 Engine Definitions
FORGE_API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"

# MASTER HIGH-RES TILE RESOLUTION
SOURCE_TILE_DIM = 1024  # Renders standalone assets natively at 1024x1024 before resizing

# ============================================================================
# FIXED PROMPT GENERATION MATRIX (Asset Type and Isolation Rules First)
# ============================================================================
# ============================================================================
# HYPER-ISOLATED SPRITE GENERATION CONFIG (Stops Full-Bleed Color Zooming)
# ============================================================================
ASSET_TYPES_CONFIG = {
    "Floor/Ground": {
        "default_qty": 4, 
        "modifier": "(Flat top-down orthographic ground tile texture:1.4), seamless tilling game texture pattern, uniform surface, stone loam soil paving"
    },
    "Walls": {
        "default_qty": 4, 
        "modifier": "(A single isolated straight front-facing wall section game sprite:1.5), isolated object centered on a solid plain light-gray background, clear distinct object borders, no flooring"
    },
    "Doors/Entrances": {
        "default_qty": 1, 
        "modifier": "(A single isolated standalone closed wooden door with an stone arch frame:1.5), game icon sprite layout, centered object isolated on a solid plain white background, distinct sharp borders"
    },
    "Decorations": {
        "default_qty": 1, 
        "modifier": "(A single isolated standalone clutter item prop:1.4), 2D game icon style, centered object isolated on a solid plain white background, clear object silhouette"
    },
    "Paths/Roads": {
        "default_qty": 1, 
        "modifier": "(A flat top-down seamless road pathway tile:1.4), clear dirt trail line or stone paving lane winding across the surface canvas, clear ground pattern"
    },
    "Hazards": {
        "default_qty": 1, 
        "modifier": "(A single isolated environmental hazard floor puddle sprite:1.4), glowing green toxic acid pool, or glowing red hot lava crack, isolated on a solid plain black background"
    },
    "Structures": {
        "default_qty": 1, 
        "modifier": "(A single isolated small structural stone tower foundation base:1.4), standalone building footprint game sprite, isolated on a solid plain white background"
    },
    "Objects": {
        "default_qty": 1, 
        "modifier": "(A single isolated closed wooden treasure chest container with iron bands:1.5), 2D game icon style sprite, centered object isolated on a solid plain white background, explicit distinct object bounds"
    }
}
class ForgeStudioUI(BoxLayout):
    def __init__(self, **kwargs):
        super(ForgeStudioUI, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 20
        self.spacing = 15
        
        # 1. Header Workspace
        self.add_widget(Label(text="SHATTERLANDS SAGA: DYNAMIC STANDALONE TILE FORGE (V3)", font_size='18sp', size_hint_y=0.08))
        
        main_layout = BoxLayout(orientation='horizontal', spacing=15, size_hint_y=0.72)
        
        # LEFT PANEL: Project Parameters Input Configuration Panel
        params_panel = BoxLayout(orientation='vertical', spacing=8)
        
        params_panel.add_widget(Label(text="Project Target Name (Output Folder Name):", halign='left', size_hint_y=0.06))
        self.project_name_input = TextInput(text="Jade_Overgrowth", multiline=False, size_hint_y=0.1)
        params_panel.add_widget(self.project_name_input)
        
        params_panel.add_widget(Label(text="Master Lore Theme / Base Prompt Vector:", halign='left', size_hint_y=0.06))
        self.master_prompt_input = TextInput(text="Ancient jade broadleaf jungle over rich tropical mud, overgrown mossy stone runes.", multiline=True, size_hint_y=0.5)
        params_panel.add_widget(self.master_prompt_input)

        # Output Resizing Geometry Workspace
        geometry_layout = GridLayout(cols=2, spacing=5, size_hint_y=0.28)
        
        geometry_layout.add_widget(Label(text="Final Tile Width (Pixels):", halign='left'))
        self.target_w_input = TextInput(text="64", multiline=False, input_filter='int')
        geometry_layout.add_widget(self.target_w_input)
        
        geometry_layout.add_widget(Label(text="Final Tile Height (Pixels):", halign='left'))
        self.target_h_input = TextInput(text="64", multiline=False, input_filter='int')
        geometry_layout.add_widget(self.target_h_input)
        
        params_panel.add_widget(geometry_layout)
        main_layout.add_widget(params_panel)
        
        # RIGHT PANEL: Asset Checklist & Variation Sliders
        checklist_panel = BoxLayout(orientation='vertical', spacing=10)
        checklist_panel.add_widget(Label(text="Configure Asset Types & Variation Quantities:", size_hint_y=0.08))
        
        scroll_view = ScrollView(size_hint_y=0.74)
        self.type_checklist = GridLayout(cols=1, size_hint_y=None, spacing=8)
        self.type_checklist.bind(minimum_height=self.type_checklist.setter('height'))
        
        self.controls = {}
        for asset_type, config in ASSET_TYPES_CONFIG.items():
            # Create a compact row wrapper for Checkbox, Label, Slider, and Qty readback label
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=45)
            
            cb = CheckBox(size_hint_x=0.08, active=True) # Checked by default for execution speed
            
            label = Label(text=asset_type, halign='left', size_hint_x=0.32)
            label.bind(size=label.setter('text_size'))
            
            # Slider adjusting variation targets dynamically from 1 to 12 variations
            slider = Slider(min=1, max=12, value=config["default_qty"], step=1, size_hint_x=0.45)
            qty_label = Label(text=f"Qty: {int(slider.value)}", size_hint_x=0.15, color=(0, 0.8, 0.8, 1))
            
            # Keep the readback text locked to slider ticks natively
            slider.bind(value=lambda instance, val, ql=qty_label: setattr(ql, 'text', f"Qty: {int(val)}"))
            
            row.add_widget(cb)
            row.add_widget(label)
            row.add_widget(slider)
            row.add_widget(qty_label)
            
            self.type_checklist.add_widget(row)
            self.controls[asset_type] = {"checkbox": cb, "slider": slider}
            
        scroll_view.add_widget(self.type_checklist)
        checklist_panel.add_widget(scroll_view)
        
        # Deployment Activation Engine
        self.deploy_button = Button(text="DEPLOY FIXED BATCH PIPELINE TO OPEN FORGE", background_color=(0, 0.5, 0, 1), size_hint_y=0.18)
        self.deploy_button.bind(on_release=self.start_generation_batch_thread)
        checklist_panel.add_widget(self.deploy_button)
        
        main_layout.add_widget(checklist_panel)
        self.add_widget(main_layout)
        
        # System Progress Log Output Monitor Panel
        self.logs_label = Label(text="System online. Ready for corrected asset generation parameters loop deployment...", halign='left', size_hint_y=0.2, color=(0.8, 0.8, 0.8, 1))
        self.logs_label.bind(size=self.logs_label.setter('text_size'))
        self.add_widget(self.logs_label)

    def log_message(self, message):
        """Thread-safe updates to UI logging label strings."""
        Clock.schedule_once(lambda dt: self._update_logs(message))

    def _update_logs(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs_label.text = f"[{timestamp}] {message}"

    def start_generation_batch_thread(self, instance):
        """Dispatches operations onto a separate thread to prevent Kivy frame-render hanging."""
        self.project_name = self.project_name_input.text.strip().replace(" ", "_")
        self.base_prompt = self.master_prompt_input.text.strip()
        
        try:
            self.target_w = int(self.target_w_input.text)
            self.target_h = int(self.target_h_input.text)
        except ValueError:
            self.log_message("ERROR: Resizing function bounds are missing or incorrect integers.")
            return

        # Map active tasks with their requested iteration variation counts
        tasks_to_run = {}
        for asset_type, control in self.controls.items():
            if control["checkbox"].active:
                tasks_to_run[asset_type] = int(control["slider"].value)
                
        if not self.project_name or not self.base_prompt or not tasks_to_run:
            self.log_message("ERROR: Missing valid naming strings, prompt matrices, or active type checkboxes.")
            return

        self.deploy_button.disabled = True
        self.deploy_button.text = "GENERATING STANDALONE ASSETS..."
        
        # Run the updated, corrected processing loop
        threading.Thread(target=self.generation_pipeline_process_loop_corrected, args=(tasks_to_run,)).start()

    def generation_pipeline_process_loop_corrected(self, tasks_to_run):
        """Sequentially triggers individual requests with INVERTED and WEIGHTED prompts."""
        self.log_message(f"PRODUCTION GENESIS: Constructing fixed pipeline layers inside 'standalone_output/{self.project_name}'...")
        
        OUTPUT_ROOT = "standalone_output"
        project_output_dir = os.path.join(OUTPUT_ROOT, f"{self.project_name}")
        os.makedirs(project_output_dir, exist_ok=True)
        
        for asset_type, variation_count in tasks_to_run.items():
            type_modifier = ASSET_TYPES_CONFIG[asset_type]["modifier"]
            type_tag = asset_type.lower().replace("/", "_").replace(" ", "_")
            
            type_output_dir = os.path.join(project_output_dir, f"{type_tag}")
            os.makedirs(type_output_dir, exist_ok=True)
            
            for v_idx in range(1, variation_count + 1):
                # FIXED INVERSION RULE: Type first, enclosed in high-weight attention tags, followed by background theme context
                final_prompt = (
                    f"({type_modifier}:1.4), styled matching a fantasy RPG sprite layout, "
                    f"isolated on a plain clean backdrop, individual standalone asset. "
                    f"Environment and Material Context: {self.base_prompt}. "
                    f"Sharp detailed game texture, high focus icon, single piece layout, distinct silhouette."
                )
                
                filename = f"{self.project_name}_{type_tag}_{v_idx}.png"
                filepath = os.path.join(type_output_dir, filename)
                
                # Heavy negative prompt enforcement to stop Stable Diffusion from making multi-tile sheets or sprawling scenes
                payload = {
                    "prompt": final_prompt,
                    "negative_prompt": "3D perspective view, camera tilt, landscape scene, background view, multiple items, collage, sheet format, split screen, text, numbers, watermark",
                    "steps": 28, 
                    "cfg_scale": 8.0, # Increased slightly to force strict prompt adherence
                    "width": SOURCE_TILE_DIM, 
                    "height": SOURCE_TILE_DIM,
                    "sampler_name": "Euler a", 
                    "batch_size": 1
                }
                
                try:
                    # Execute direct endpoint handshakes
                    response = requests.post(FORGE_API_URL, json=payload, timeout=120)
                    if response.status_code == 200:
                        r_json = response.json()
                        img_data = base64.b64decode(r_json["images"][0])
                        raw_tile_img = Image.open(io.BytesIO(img_data))
                        
                        # Apply your custom image resizing function directly on save
                        resized_tile = raw_tile_img.resize((self.target_w, self.target_h), Image.Resampling.LANCZOS)
                        resized_tile.save(filepath, "PNG")
                        
                        # Direct minimal tracking response pushed to UI HUD monitor
                        Clock.schedule_once(lambda dt, cur=v_idx, tot=variation_count, t=asset_type: setattr(self.logs_label, 'text', f"Rendered isolated standalone asset {cur}/{tot} for type '{t}'..."))
                    else:
                        self.log_message(f"REJECTED: Open Forge aborted prompt validation. Status Code: {response.status_code}")
                except Exception as e:
                    self.log_message(f"CRITICAL: Handshake connection dropped with Open Forge API: {e}")
                    
        self.log_message(f"DEPLOYMENT RESOLVED: Fixed asset production complete inside: 'standalone_output/{self.project_name}/'")
        Clock.schedule_once(lambda dt: self.reset_deployment_button())

    def reset_deployment_button(self):
        self.deploy_button.disabled = False
        self.deploy_button.text = "DEPLOY FIXED BATCH PIPELINE TO OPEN FORGE"

class ShatterlandsDynamicStudioApp(App):
    def build(self):
        Window.size = (1024, 768)
        Window.title = "Shatterlands Saga - Fixed Standalone Asset Studio (V3 Engine)"
        return ForgeStudioUI()

if __name__ == "__main__":
    # Launch asset production pipeline
    ShatterlandsDynamicStudioApp().run()