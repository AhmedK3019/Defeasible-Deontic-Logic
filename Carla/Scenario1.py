import carla
import time
import math
import os
import sys
sys.path.append(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic\Python")
from ddl_V2 import DDLEngine

def main():
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    
    # Force a clean, straight map
    world = client.load_world('Town07')

    traffic_lights = world.get_actors().filter('traffic.traffic_light')
    for tl in traffic_lights:
        tl.freeze(True)
    
    blueprint_library = world.get_blueprint_library()
    
    # Keep track of what you spawn so you can delete it
    actor_list = []

    # Initialize the Logic Engine ONCE here
    root_folder = r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic"
    logic_engine = DDLEngine(root_folder)

    try:
        # 1. Spawn EXACTLY one Mercedes (Ego Vehicle)
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100') # Red
        spawn_points = world.get_map().get_spawn_points()
        
        car_spawn = spawn_points[55] # Fallback
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned")

        # --- THE STATIC CAMERA ---
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 8)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 8)
        cam_z = car_transform.location.z + 3.0
        
        cam_location = carla.Location(x=cam_x, y=cam_y, z=cam_z)
        spectator.set_transform(carla.Transform(cam_location, car_transform.rotation))

        # 2. Spawn EXACTLY one Pedestrian (20 meters ahead)
        pedestrian_bp = blueprint_library.find('static.prop.barrel')
        
        forward_vector = car_spawn.get_forward_vector()
        ped_x = car_spawn.location.x + (forward_vector.x * 20.0)
        ped_y = car_spawn.location.y + (forward_vector.y * 20.0)
        ped_z = car_spawn.location.z
        
        pedestrian_loc = carla.Location(x=ped_x, y=ped_y, z=ped_z)
        pedestrian_spawn = spawn_points[13]

        pedestrian = world.spawn_actor(pedestrian_bp, pedestrian_spawn)
        actor_list.append(pedestrian)
        print("✅ Pedestrian Spawned")

        # 3. Spawn EXACTLY one Oncoming Car (40 meters ahead, perfectly in the left lane)
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200') # Blue
        oncoming_transform = spawn_points[3]
        
        # ---> TOGGLE THIS TO TEST THE BASE CASE vs DEFEATER <---
        oncoming_car = None 
        # oncoming_car = world.spawn_actor(audi_bp, oncoming_transform)
        
        actor_list.append(oncoming_car)
        print("✅ Oncoming Traffic Spawned safely on the road")
        
        if oncoming_car is not None:
            oncoming_car.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0))

        # --- ACTUATION ---
        ego_vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0))
        print("🚗 Vehicle in motion...")

        # 4. The Perception Loop
        while True:
            car_loc = ego_vehicle.get_location()
            ped_loc = pedestrian.get_location()
            distance = math.hypot(ped_loc.x - car_loc.x, ped_loc.y - car_loc.y)
            
            print(f"\rDistance to hazard: {distance:.2f} meters   ", end="")

            if distance < 12.0:
                print("\n\n🚨 CRITICAL DISTANCE REACHED (< 12m) 🚨")
                
                # Immediate Safety Override
                ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                ego_vehicle.set_light_state(carla.VehicleLightState.Brake)
                
                # DYNAMIC Fact Generation
                print("📝 Reading CARLA sensors to build live facts...")
                live_facts = ["driving", "obstacle", "short_distance"]
                
                # Sensor: Oncoming Traffic Radar
                if oncoming_car is not None:
                    oncoming_loc = oncoming_car.get_location()
                    oncoming_dist = math.hypot(oncoming_loc.x - car_loc.x, oncoming_loc.y - car_loc.y)
                    if oncoming_dist < 30.0:
                        live_facts.append("oncoming_traffic")
                        print(f"⚠️ ONCOMING TRAFFIC DETECTED at {oncoming_dist:.1f}m!")
                
                # Sensor: Lane Markings
                waypoint = world.get_map().get_waypoint(car_loc)
                if waypoint.left_lane_marking.type == carla.LaneMarkingType.Solid:
                    live_facts.append("solid_line")
                else:
                    live_facts.append("dashed_line") 

                # Combine Facts and Rules into memory
                facts_header = "# Facts\n" + "\n".join(live_facts) + "\n\n"
                rules_block = (
                    "# Rules\n"
                    "n_legal: driving, solid_line => [O]~cross_line\n"
                    "n_safe: obstacle, short_distance => [O]cross_line\n"
                    "n_critical: obstacle, oncoming_traffic => [O]~cross_line\n\n"
                    "# Superiority\n"
                    "n_safe > n_legal\n"
                    "n_critical > n_safe\n"
                )
                
                scenario_content = facts_header + rules_block
                
                # --- IN-MEMORY EVALUATION (No Subprocess, No File Writes) ---
                print("🧠 Querying Clingo directly in memory...")
                clingo_output = logic_engine.evaluate(scenario_content)
                
                print("\n--- CLINGO VERDICT ---")
                print(f"Obligations: {clingo_output}")
                print("----------------------\n")

                # Resolve Actuation based on string match
                if "non(cross_line)" in clingo_output:
                    print("⚖️ Resolution: MAINTAIN BRAKE (Critical Safety Overrides Evasion)")
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0))
                    time.sleep(4.0)
                    
                elif "cross_line" in clingo_output:
                    print("⚖️ Resolution: CROSS LINE (Safety > Legality)")
                    print("🚗 Executing 'Pass and Return' Maneuver...")
                    
                    ego_vehicle.set_light_state(carla.VehicleLightState.LeftBlinker) 
                    
                    # 1. THE EVASION
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=-0.2, brake=0.0))
                    time.sleep(1.3) 
                    
                    # 2. LEVEL OUT
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=0.2, brake=0.0))
                    time.sleep(1.2)
                    
                    # 3. THE PASS
                    ego_vehicle.set_light_state(carla.VehicleLightState.NONE) 
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=0.0, brake=0.0))
                    time.sleep(1.0) 

                    # 4. THE RECOVERY
                    ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=0.3, brake=0.0))
                    time.sleep(0.8)

                    # 5. LEVEL OUT
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=-0.32, brake=0.0))
                    time.sleep(0.8) 
                    
                    # 6. ESCAPE (Keep moving slightly to avoid stalling the AI handoff)
                    ego_vehicle.set_light_state(carla.VehicleLightState.NONE)
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0, brake=0.0))
                    time.sleep(1.0)

                    # --- THE AI HANDOFF ---
                    print("🤖 Handing control back to CARLA Autopilot...")
                    ego_vehicle.set_autopilot(True)
                    time.sleep(5.0)
                    
                else:
                    print("⚖️ Resolution: MAINTAIN BRAKE (Fallback)")
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0))
                    time.sleep(4.0)

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