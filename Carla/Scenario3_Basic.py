import carla
import time
import math
import os
import sys

# Ensure this path points to your actual DDL Python folder
sys.path.append(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic\Python")
from ddl_V2 import DDLEngine

def main():
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    
    print("🌍 Loading Town07 (Rural Environment)...")
    world = client.load_world('Town07')

    blueprint_library = world.get_blueprint_library()
    actor_list = []

    # Initialize the Logic Engine ONCE here (Upgraded from subprocess)
    root_folder = r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic"
    logic_engine = DDLEngine(root_folder)

    try:
        # 1. Spawn EXACTLY one Mercedes (Ego Vehicle)
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100') # Red
        spawn_points = world.get_map().get_spawn_points()
        
        # ---> CHANGE THIS TO YOUR TOWN 07 SPAWN NUMBER <---
        car_spawn = spawn_points[55] 
        
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned")

        # --- THE STATIC CAMERA ---
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 8)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 8)
        cam_z = car_transform.location.z + 4.0
        
        cam_location = carla.Location(x=cam_x, y=cam_y, z=cam_z)
        spectator.set_transform(carla.Transform(cam_location, car_transform.rotation))

        # 2. Spawn EXACTLY one Pedestrian (15 meters ahead, shifted to right edge)
        walker_bps = blueprint_library.filter('walker.pedestrian.*')
        pedestrian_bp = walker_bps[0]  
        
        forward_vector = car_spawn.get_forward_vector()
        right_vector = car_spawn.get_right_vector()
        
        ped_x = car_spawn.location.x + (forward_vector.x * 15.0)
        ped_y = car_spawn.location.y + (forward_vector.y * 15.0)
        
        # Shift pedestrian to the right edge of the lane
        shift_amount = 1.2 
        ped_x += (right_vector.x * shift_amount)
        ped_y += (right_vector.y * shift_amount)
        
        # Safely drop from the sky to avoid ground collisions
        ped_z = car_spawn.location.z + 2.0 
        
        pedestrian_loc = carla.Location(x=ped_x, y=ped_y, z=ped_z)
        pedestrian_spawn = carla.Transform(pedestrian_loc, car_spawn.rotation)
        
        pedestrian = world.spawn_actor(pedestrian_bp, pedestrian_spawn)
        actor_list.append(pedestrian)
        print("✅ Pedestrian Spawned on Right Edge")

        # --- MAKE THE PEDESTRIAN WALK ---
        walker_control = carla.WalkerControl()
        walker_control.direction = car_spawn.get_forward_vector() 
        walker_control.speed = 1 # 1.5 m/s
        pedestrian.apply_control(walker_control)
        print("🚶‍♂️ Pedestrian is walking")

        # 3. Spawn Oncoming Car (BY FORCE)
        # Bypassing the map API and using pure vector math
        
        # 1. Start at the ego vehicle's location
        forward_vector = car_spawn.get_forward_vector()
        right_vector = car_spawn.get_right_vector()
        
        # 2. Push it 45 meters forward
        audi_x = car_spawn.location.x + (forward_vector.x * 45.0)
        audi_y = car_spawn.location.y + (forward_vector.y * 45.0)
        
        # 3. Force it 3.5 meters to the LEFT (Negative Right Vector)
        shift_left = -3.5 
        audi_x += (right_vector.x * shift_left)
        audi_y += (right_vector.y * shift_left)
        
        # 4. Safe drop from the sky to avoid ground collisions
        audi_z = car_spawn.location.z + 2.0
        audi_loc = carla.Location(x=audi_x, y=audi_y, z=audi_z)
        
        # 5. Rotate the car 180 degrees so it drives AT the Mercedes
        audi_rot = car_spawn.rotation
        audi_rot.yaw += 180.0 
        
        audi_spawn = carla.Transform(audi_loc, audi_rot)
        
        # 6. Summon
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200') # Blue
        
        # ---> CHANGE TO oncoming_car = None TO TEST THE BASE CASE <---
        oncoming_car = world.spawn_actor(audi_bp, audi_spawn)
        actor_list.append(oncoming_car)
        print("✅ FORCED Oncoming Traffic Spawned via Geometry")
        
        # Tell the Audi to drive straight
        if oncoming_car is not None:
            oncoming_car.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0))

        # --- THE BLINDFOLDED AI (Handles the Curve) ---
        tm = client.get_trafficmanager(8000)
        tm.global_percentage_speed_difference(50.0) # Drive slowly
        tm.ignore_walkers_percentage(ego_vehicle, 100) # 100% chance to ignore pedestrian
        
        ego_vehicle.set_autopilot(True)
        print("🤖 CARLA AI is steering the curve (Ignoring Pedestrians)...")

        # 4. The Perception Loop
        while True:
            car_loc = ego_vehicle.get_location()
            ped_loc = pedestrian.get_location()
            distance = math.hypot(ped_loc.x - car_loc.x, ped_loc.y - car_loc.y)
            
            print(f"\rDistance to hazard: {distance:.2f} meters   ", end="")

            if distance < 12.0:
                print("\n\n🚨 CRITICAL DISTANCE REACHED (< 12m) 🚨")
                
                # INSTANTLY KILL THE AUTOPILOT
                ego_vehicle.set_autopilot(False)
                
                # Immediate safety brake while logic calculates
                ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                
                print("📝 Reading CARLA sensors to build live facts...")
                live_facts = ["driving"]
                
                # DYNAMIC SENSOR 1: Pedestrian detected inside safety buffer
                live_facts.append("pedestrian")
                
                # DYNAMIC SENSOR 2: Check for oncoming traffic
                if oncoming_car is not None:  # DEFENSIVE CHECK
                    oncoming_loc = oncoming_car.get_location()
                    oncoming_dist = math.hypot(oncoming_loc.x - car_loc.x, oncoming_loc.y - car_loc.y)
                    if oncoming_dist < 40.0:
                        live_facts.append("oncoming_traffic")
                        print(f"⚠️ ONCOMING TRAFFIC DETECTED at {oncoming_dist:.1f}m!")
                
                # DYNAMIC SENSOR 3: Read Road Paint
                waypoint = world.get_map().get_waypoint(car_loc)
                if waypoint.left_lane_marking.type in [carla.LaneMarkingType.Solid, carla.LaneMarkingType.SolidSolid]:
                    live_facts.append("solid_line")
                    print("⚠️ SOLID LINE DETECTED")
                else:
                    live_facts.append("dashed_line")

                # Stitch facts together
                facts_header = "# Facts\n" + "\n".join(live_facts) + "\n\n"
                
                # STITCHING YOUR EXACT LOGIC INTO THE RULES BLOCK
                rules_block = (
                    "# Strict Rules\n"
                    "r_phys: pedestrian -> buffer_required\n\n"
                    "# Defeasible Rules (norms)\n"
                    "r_legal: solid_line => [O]~cross_line\n"
                    "r_safe: buffer_required => [O]provide_buffer & [O]cross_line\n"
                    "r_critical: oncoming_traffic, pedestrian => [O]~cross_line & [O]~provide_buffer & [O]trail_pedestrian\n\n"
                    "# Superiority\n"
                    "r_safe > r_legal\n"
                    "r_critical > r_safe\n"
                )
                
                # Combine Dynamic Facts with Static Rules
                scenario_content = facts_header + rules_block
                
                # --- IN-MEMORY EVALUATION (Upgraded) ---
                print("🧠 Querying Clingo directly in memory...")
                clingo_output = logic_engine.evaluate(scenario_content)
                clingo_string = str(clingo_output)

                print("\n--- CLINGO VERDICT ---")
                print(f"Raw Output: {clingo_string}")
                print("----------------------\n")
                    
                # --- THE ACTUATION ---
                if "trail_pedestrian" in clingo_string:
                    print("⚖️ Resolution: TRAIL PEDESTRIAN (Oncoming traffic blocks pass)")
                    
                    # Testing your slow throttle theory!
                    print("🚗 Applying Open-Loop Throttle to trail...")
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.2, steer=0.0, brake=0.0, manual_gear_shift=True, gear=1))
                    
                    # Let the script sleep for a while so you can watch what happens 
                    # as the 10% throttle outpaces the 1.5 m/s pedestrian over time.
                    time.sleep(10.0) 
                        
                elif "cross_line" in clingo_string:
                    print("⚖️ Resolution: CROSS LINE (Buffer Required > Legal Line)")
                    ego_vehicle.set_light_state(carla.VehicleLightState.LeftBlinker) 
                    
                    # Force gear 1 for sudden movement
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=-0.4, brake=0.0, manual_gear_shift=True, gear=1))
                    time.sleep(1.5) 
                    
                    # RECOVERY MANEUVER 
                    ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=0.4, brake=0.0))
                    time.sleep(1.5)
                    ego_vehicle.set_light_state(carla.VehicleLightState.NONE)
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    time.sleep(2.0)
                        
                break
            
            time.sleep(0.05)
            
        time.sleep(4.0)

    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    finally:
        print("\nCleaning up the world...")
        for actor in actor_list:
            # FIX: Added 'actor is not None' to prevent AttributeErrors on cleanup
            if actor is not None and actor.is_alive:
                actor.destroy()
        print("✅ Cleanup complete.")

if __name__ == '__main__':
    main()