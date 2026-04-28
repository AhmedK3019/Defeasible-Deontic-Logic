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


    root_folder = r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic"
    logic_engine = DDLEngine(root_folder)

    try:
        # --- FREEZE ALL TRAFFIC LIGHTS TO RED ---
        traffic_lights = world.get_actors().filter('traffic.traffic_light')
        for tl in traffic_lights:
            tl.set_state(carla.TrafficLightState.Red)
            tl.freeze(True)
        print("🛑 All traffic lights locked to RED.")

        # 1. Spawn EXACTLY one Mercedes (Ego Vehicle) at Spawn 4
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100') # Red
        spawn_points = world.get_map().get_spawn_points()
        
        car_spawn = spawn_points[4] 
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned at Index 4")

        # --- THE INITIAL STATIC CAMERA ---
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 15)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 15)
        cam_z = car_transform.location.z + 8.0 
        cam_location = carla.Location(x=cam_x, y=cam_y, z=cam_z)
        cam_rotation = car_transform.rotation
        cam_rotation.pitch -= 15.0
        spectator.set_transform(carla.Transform(cam_location, cam_rotation))

        # 2. Spawn the Ambulance at Spawn 75
        amb_spawn = spawn_points[75]
        amb_bp = blueprint_library.find('vehicle.ford.ambulance')
        
        ambulance = world.spawn_actor(amb_bp, amb_spawn)
        actor_list.append(ambulance)
        print("🚑 Ambulance Spawned at Index 75")
        
        ambulance.set_light_state(carla.VehicleLightState(carla.VehicleLightState.Special1 | carla.VehicleLightState.Special2))

        # 3. Spawn Cross Traffic (The Defeater) 
        forward_vector = car_spawn.get_forward_vector()
        right_vector = car_spawn.get_right_vector()
        
        intersection_center_x = car_spawn.location.x + (forward_vector.x * 35.0)
        intersection_center_y = car_spawn.location.y + (forward_vector.y * 35.0)
        
        # # PUSH THE AUDI LEFT OF THE INTERSECTION
        # cross_x = intersection_center_x + (right_vector.x * -35.0)
        # cross_y = intersection_center_y + (right_vector.y * -35.0)
        # cross_z = car_spawn.location.z + 1.0
        
        # cross_loc = carla.Location(x=cross_x, y=cross_y, z=cross_z)
        # cross_rot = car_spawn.rotation
        # cross_rot.yaw += 90.0 
        cross_spawn = spawn_points[29]

        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200')
        
        # To test the "Safe" scenario where the Mercedes moves, change this to: cross_car = None
        cross_car = world.spawn_actor(audi_bp, cross_spawn)
        # cross_car = None
        actor_list.append(cross_car)
        print("✅ Cross Traffic (Audi) Spawned left of the intersection")

        # --- ORCHESTRATION ---
        tm = client.get_trafficmanager(8000)
        
        # Mercedes
        tm.vehicle_percentage_speed_difference(ego_vehicle, -50.0) 
        ego_vehicle.set_autopilot(True)
        
        # Ambulance: Fast tailgating
        tm.ignore_lights_percentage(ambulance, 100)
        tm.auto_lane_change(ambulance, False)
        tm.distance_to_leading_vehicle(ambulance, 2.0)
        tm.vehicle_percentage_speed_difference(ambulance, -50.0) 
        ambulance.set_autopilot(True)

        # Audi: Active cross-traffic (NOTE: No longer ignoring lights, it will get a green light)
        if cross_car is not None:
            tm.vehicle_percentage_speed_difference(cross_car, -20.0) 
            cross_car.set_autopilot(True)

        print("🤖 Vehicles in motion. Waiting for Mercedes to hit the red light trap...")

        # 4. The Perception Loop
        while True:
            # SCOPING FIX: Defined at the very top of the loop
            car_loc = ego_vehicle.get_location()
            amb_loc = ambulance.get_location()
            
            amb_dist = math.hypot(amb_loc.x - car_loc.x, amb_loc.y - car_loc.y)
            print(f"\rAmbulance Distance: {amb_dist:.2f} meters   ", end="")

            velocity = ego_vehicle.get_velocity()
            speed = math.hypot(velocity.x, velocity.y)
            
            # EMERGENCY TRIGGER: Mercedes stopped at light, Ambulance arrived
            if speed < 0.5 and amb_dist < 12.0:
                print("\n\n🚨 SIRENS DETECTED (< 12m) AT STOPPED LIGHT 🚨")
                
                ego_vehicle.set_autopilot(False)
                ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                
                if ambulance is not None:
                    ambulance.set_autopilot(False)
                    ambulance.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                print("📝 Reading CARLA sensors to build live facts...")
                live_facts = []
                
                # --- DYNAMIC SENSOR 0: Velocity Tracking ---
                velocity = ego_vehicle.get_velocity()
                speed = math.hypot(velocity.x, velocity.y)
                if speed > 0.1: 
                    live_facts.append("driving")
                
                # --- DYNAMIC SENSOR 1: Red Light Camera ---
                if ego_vehicle.is_at_traffic_light():
                    live_facts.append("red_light")
                    print("⚠️ RED LIGHT DETECTED")
                else:
                    print("ℹ️ No red light detected by CARLA sensors.") 
                
                # --- DYNAMIC SENSOR 2: Emergency Siren Proximity ---
                # Triggered mathematically by the amb_dist < 12.0 loop above
                live_facts.append("ambulance_vehicle") 
                
                if ego_vehicle.is_at_traffic_light():
                    live_facts.append("red_light")
                    print("⚠️ RED LIGHT DETECTED")
                else:
                    print("ℹ️ No red light detected by CARLA sensors.") 
                
                live_facts.append("ambulance_vehicle")
                
                # Check Audi and manipulate its traffic light
                if cross_car is not None:  
                   
                    audi_light = cross_car.get_traffic_light()
                    if audi_light is not None and audi_light.get_state() != carla.TrafficLightState.Green:
                        audi_light.set_state(carla.TrafficLightState.Green)
                        audi_light.freeze(True)
                        print("🟢 The Audi's traffic light has been forced to GREEN.")
                    
                    cross_loc = cross_car.get_location()
                    cross_dist = math.hypot(cross_loc.x - car_loc.x, cross_loc.y - car_loc.y)
                    if cross_dist < 45.0:
                        live_facts.append("traffic")
                        print(f"⚠️ MOVING CROSS TRAFFIC DETECTED at {cross_dist:.1f}m! Intersection unsafe.")

                facts_header = "# Facts\n" + "\n".join(live_facts) + "\n\n"

                
                rules_block = (
                    "# Strict rules\n"
                    "r1: ambulance_vehicle -> emergency_vehicle\n\n"
                    
                    "# Defeasible norms\n"
                    "r_legal: red_light => [O]~enter_intersection\n"
                    "r_safe: emergency_vehicle => [O]clear_path & [O]enter_intersection\n"
                    "r_critical: traffic => [O]~enter_intersection\n\n"
                    
                    "# Priority Relations\n"
                    "r_safe > r_legal\n"
                    "r_critical > r_safe\n"
                )
                
                scenario_content = facts_header + rules_block

                # --- IN-MEMORY EVALUATION ---
                print("🧠 Querying Clingo directly in memory...")
                clingo_output = logic_engine.evaluate(scenario_content)
                clingo_string = str(clingo_output)

                print("\n--- CLINGO VERDICT ---")
                print(f"Raw Output: {clingo_string}")
                print("----------------------\n")

        
                if "non(enter_intersection)" in clingo_string:
                    print("⚖️ Resolution: TRAPPED (Collision Avoidance/Law > Emergency). Holding brakes.")
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    time.sleep(8.0) 
                        
                elif "enter_intersection" in clingo_string:
                    print("⚖️ Resolution: ENTERING INTERSECTION (Emergency Protocol > Red Light Law).")
                    
                    ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                    
                    # Force gear 1 to overcome a dead stop
                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.6, steer=0.0, brake=0.0, manual_gear_shift=True, gear=1))
                    time.sleep(2.0)

                    ego_vehicle.apply_control(carla.VehicleControl(throttle=0.6, steer=0.45, brake=0.0))
                    time.sleep(1.5) 
                    
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    ego_vehicle.set_light_state(carla.VehicleLightState.Special1)
                    
                    if ambulance is not None:
                        print("🚑 Re-engaging Traffic Manager (Override active)!")
                        ambulance.set_autopilot(True)
                        tm.ignore_lights_percentage(ambulance, 100)
                        tm.ignore_vehicles_percentage(ambulance, 100) 
                        tm.auto_lane_change(ambulance, False)
                        tm.vehicle_percentage_speed_difference(ambulance, -300.0) 
                        
                    time.sleep(6.0)
                
                # Exit the while loop after handling the emergency scenario
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