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
        # 1. Spawn one Mercedes (Ego Vehicle) at Spawn 59
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100') # Red
        spawn_points = world.get_map().get_spawn_points()
        
        car_spawn = spawn_points[59] 
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned at Index 59")

        # --- THE STATIC CAMERA (High up to see the intersection) ---
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 15)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 15)
        cam_z = car_transform.location.z + 10.0 
        
        cam_location = carla.Location(x=cam_x, y=cam_y, z=cam_z)
        cam_rotation = car_transform.rotation
        cam_rotation.pitch -= 20.0 # Pointing downward
        spectator.set_transform(carla.Transform(cam_location, cam_rotation))

        # 2. Spawn the Roadblock at Spawn 74
        obstacle_spawn = spawn_points[74]
        truck_bp = blueprint_library.find('vehicle.carlamotors.carlacola')
        
        # Rotate the truck 90 degrees so it blocks the road
        obstacle_rot = obstacle_spawn.rotation
        obstacle_rot.yaw += 90.0
        obstacle_transform = carla.Transform(obstacle_spawn.location, obstacle_rot)
        
        roadblock = world.spawn_actor(truck_bp, obstacle_transform)
        actor_list.append(roadblock)
        print("🚧 Impassable Roadblock (Truck) Spawned at Index 74")

        # 3. Spawn Rear Traffic (The Defeater) 20 meters directly behind the Mercedes
        # ---> CHANGE TO `rear_car = None` TO TEST THE ESCAPE BASE CASE <---
        
        forward_vector = car_spawn.get_forward_vector()
        
        # Multiply by -20.0 to push it 20 meters backwards along the same vector
        rear_x = car_spawn.location.x + (forward_vector.x * -15.0)
        rear_y = car_spawn.location.y + (forward_vector.y * -15.0)
        rear_z = car_spawn.location.z + 1.0 # Safe drop from the sky
        
        rear_loc = carla.Location(x=rear_x, y=rear_y, z=rear_z)
        rear_spawn = carla.Transform(rear_loc, car_spawn.rotation)
        
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200') # Blue
        
        rear_car = world.spawn_actor(audi_bp, rear_spawn)
        # rear_car = None  # Comment this line to spawn the rear traffic
        actor_list.append(rear_car)
        print("✅ Rear Traffic Spawned exactly 20 meters behind Ego Vehicle")

        # --- (For Ego Vehicle) ---
        tm = client.get_trafficmanager(8000)
        tm.vehicle_percentage_speed_difference(ego_vehicle, 60.0) # Drive 60% of limit to let Audi catch up
        tm.ignore_walkers_percentage(ego_vehicle, 100)
        ego_vehicle.set_autopilot(True)
        print("🤖 Mercedes AI is creeping towards the roadblock...")

        # 4. The Perception Loop
        while True:
            car_loc = ego_vehicle.get_location()
            obstacle_loc = roadblock.get_location()
            distance = math.hypot(obstacle_loc.x - car_loc.x, obstacle_loc.y - car_loc.y)
            
            print(f"\rDistance to Roadblock: {distance:.2f} meters   ", end="")

            # --- CUSTOM FOLLOWER LOGIC FOR THE AUDI ---
            if rear_car is not None:
                rear_loc = rear_car.get_location()
                gap = math.hypot(car_loc.x - rear_loc.x, car_loc.y - rear_loc.y)
                
                # If gap is more than 15m, speed up
                if gap > 15.0:
                    rear_car.apply_control(carla.VehicleControl(throttle=0.6, brake=0.0))
                # If gap is less than 10m, hit the brakes so we don't crash
                elif gap < 10.0:
                    rear_car.apply_control(carla.VehicleControl(throttle=0.0, brake=0.6))
                # Otherwise, just coast to maintain speed
                else:
                    rear_car.apply_control(carla.VehicleControl(throttle=0.2, brake=0.0))
            # ------------------------------------------

            if distance < 12.0:
                print("\n\n🚨 IMPASSABLE HAZARD DETECTED (< 12m) 🚨")
                
                # INSTANTLY KILL BOTH AUTOPILOTS
                ego_vehicle.set_autopilot(False)
                ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                
                # Stop the Audi exactly where it is
                if rear_car is not None:
                    rear_car.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                
                print("📝 Reading CARLA sensors to build live facts...")
                live_facts = []
                
                # --- DYNAMIC SENSOR 0: Velocity Tracking ---
                velocity = ego_vehicle.get_velocity()
                speed = math.hypot(velocity.x, velocity.y)
                if speed > 0.1: # Threshold to account for micro-physics jitter
                    live_facts.append("driving")

                # --- FORCED CONTEXT: One-Way Street ---
                # Forced to True for Scenario 4 to guarantee a Legal vs. Safe conflict
                live_facts.append("one_way_street")
                
               # --- DYNAMIC SENSOR 1: Forward Hazard Detection ---
                # Get all vehicles and obstacles in the world
                vehicles = list(world.get_actors().filter('vehicle.*'))
                props = list(world.get_actors().filter('static.prop.*'))
                possible_hazards = vehicles + props
                hazard_detected = False

                for actor in possible_hazards:
                    if actor.id == ego_vehicle.id:
                        continue
                    
                    # Calculate distance and relative position
                    loc = actor.get_location()
                    dist = math.hypot(loc.x - car_loc.x, loc.y - car_loc.y)
                    
                    # If anything is closer than 12m, it's a hazard
                    if dist < 12.0:
                        hazard_detected = True
                        break

                if hazard_detected:
                    live_facts.append("hazard")
                # DYNAMIC SENSOR 2: Rear Radar
                if rear_car is not None:  
                    rear_loc = rear_car.get_location()
                    rear_dist = math.hypot(rear_loc.x - car_loc.x, rear_loc.y - car_loc.y)
                    if rear_dist < 30.0:
                        live_facts.append("rear_traffic")
                        print(f"⚠️ REAR TRAFFIC DETECTED at {rear_dist:.1f}m! Reverse path blocked.")

                facts_header = "# Facts\n" + "\n".join(live_facts) + "\n\n"
                
                rules_block = (
                    "# Strict Rules\n"
                    "r_phys: hazard -> escape_required\n\n"
                    "# Defeasible Rules (norms)\n"
                    "r_legal: one_way_street => [O]~drive_wrong_way\n"
                    "r_safe: escape_required => [O]drive_wrong_way\n"
                    "r_critical: rear_traffic, hazard => [O]~drive_wrong_way & [O]wait\n\n"
                    "# Superiority\n"
                    "r_safe > r_legal\n"
                    "r_critical > r_safe\n"
                )
                
                scenario_content = facts_header + rules_block
                
                # --- IN-MEMORY EVALUATION (Upgraded) ---
                print("🧠 Querying Clingo directly in memory...")
                clingo_output = logic_engine.evaluate(scenario_content)
                clingo_string = str(clingo_output)

                print("\n--- CLINGO VERDICT ---")
                print(f"Raw Output: {clingo_string}")
                print("----------------------\n")
                    
                # --- THE ACTUATION ---
                if "wait" in clingo_string:
                    print("⚖️ Resolution: TRAPPED (Collision Avoidance > Escape). Holding brakes.")
                    ego_vehicle.set_light_state(carla.VehicleLightState.Brake)
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    time.sleep(10.0) 
                        
                elif "drive_wrong_way" in clingo_string:
                    print("⚖️ Resolution: REVERSING WRONG WAY (Escape Hazard > One-Way Law).")
                    
                    # Turn on Reverse Lights
                    ego_vehicle.set_light_state(carla.VehicleLightState.Reverse) 
                    
                    # Apply REVERSE flag to VehicleControl
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0, brake=0.0, reverse=True, manual_gear_shift=True, gear=-1))
                    time.sleep(5.0) 
                    
                    # Stop safely (Shift back to neutral/forward)
                    ego_vehicle.set_light_state(carla.VehicleLightState.Brake)
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0, reverse=False, manual_gear_shift=True, gear=1))
                    time.sleep(2.0)
                        
                break
            
            time.sleep(0.05)
            
        time.sleep(4.0)

    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    finally:
        print("\nCleaning up the world...")
        for actor in actor_list:
        
            if actor is not None and actor.is_alive:
                actor.destroy()
        print("✅ Cleanup complete.")

if __name__ == '__main__':
    main()