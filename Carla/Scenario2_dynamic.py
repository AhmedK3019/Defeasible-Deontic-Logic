import keyboard
import carla
import time
import math
import os
import sys

sys.path.append(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic\Python")
from ddl_V2 import DDLEngine

saved_states = {}

def toggle_pause(actor_list, is_paused):
    if is_paused:
        print("\n📸 PAUSED! Freezing actors perfectly...")
        for actor in actor_list:
            if actor is not None and actor.is_alive:
                if 'vehicle' in actor.type_id:
                    saved_states[actor.id] = {
                        'control': actor.get_control(),
                        'velocity': actor.get_velocity(),
                        'angular': actor.get_angular_velocity()
                    }
                    actor.set_simulate_physics(False)
    else:
        print("\n▶️ UNPAUSED! Resuming exact maneuver...")
        for actor in actor_list:
            if actor is not None and actor.is_alive:
                if 'vehicle' in actor.type_id:
                    actor.set_simulate_physics(True)
                    if actor.id in saved_states:
                        state = saved_states[actor.id]
                        actor.apply_control(state['control'])
                        actor.set_target_velocity(state['velocity'])
                        actor.set_target_angular_velocity(state['angular'])
    return is_paused


def run_trial(client, world, tm, blueprint_library, logic_engine):
    print(f"\n========================================")
    print(f"🚀 STARTING SINGLE DYNAMIC TRIAL")
    print(f"========================================")
    
    actor_list = []
    
    try:
        # 1. Spawn EXACTLY one Mercedes (Ego Vehicle) at Spawn 4
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100')
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
        
        cross_spawn = spawn_points[29]
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200')
        
        cross_car = world.spawn_actor(audi_bp, cross_spawn)
        
        if cross_car is not None:
            actor_list.append(cross_car)
            print("✅ Cross Traffic (Audi) Spawned left of the intersection")

        # --- ORCHESTRATION ---
        tm.vehicle_percentage_speed_difference(ego_vehicle, -50.0) 
        ego_vehicle.set_autopilot(True)
        
        tm.ignore_lights_percentage(ambulance, 100)
        tm.auto_lane_change(ambulance, False)
        tm.distance_to_leading_vehicle(ambulance, 2.0)
        tm.vehicle_percentage_speed_difference(ambulance, -50.0) 
        ambulance.set_autopilot(True)

        if cross_car is not None:
            tm.vehicle_percentage_speed_difference(cross_car, 0.0) 
            tm.set_route(cross_car, ['Straight', 'Straight', 'Straight'])
            tm.ignore_vehicles_percentage(cross_car, 100)
            cross_car.set_autopilot(True)

        print("🤖 Vehicles in motion. Waiting for Mercedes to hit the red light trap...")
        
        is_paused = False
        maneuver_phase = False
        ambulance_released = False
        inference_log = []

        # 4. The Continuous Perception & Control Loop
        while True:
            # Handle manual pause
            if keyboard.is_pressed('p'):
                is_paused = not is_paused
                toggle_pause(actor_list, is_paused)
                time.sleep(0.5) 

            if is_paused:
                time.sleep(0.05)
                continue 

            car_loc = ego_vehicle.get_location()
            amb_loc = ambulance.get_location()
            car_fwd = ego_vehicle.get_transform().get_forward_vector()
            
            amb_dist = math.hypot(amb_loc.x - car_loc.x, amb_loc.y - car_loc.y)
            velocity = ego_vehicle.get_velocity()
            speed = math.hypot(velocity.x, velocity.y)

            # --- PHASE TRANSITION: Wait for the trap to trigger ---
            if not maneuver_phase:
                sys.stdout.write(f"\rWaiting... Ambulance Dist: {amb_dist:.2f}m | Ego Speed: {speed:.2f}m/s   ")
                sys.stdout.flush()
                
                # EMERGENCY TRIGGER: Mercedes stopped at light, Ambulance arrived
                if speed < 0.5 and amb_dist < 8.0:
                    print("\n\n🚨 SIRENS DETECTED AT STOPPED LIGHT. ENTERING DYNAMIC MANEUVER PHASE 🚨")
                    ego_vehicle.set_autopilot(False)
                    maneuver_phase = True
                    maneuver_start_loc = car_loc
            
            # --- MANEUVER PHASE: Dynamic Closed-Loop Control ---
            if maneuver_phase:
                live_facts = []
                
                # Base Facts
                if speed > 0.1: 
                    live_facts.append("driving")
                if ego_vehicle.is_at_traffic_light():
                    live_facts.append("red_light")
                live_facts.append("ambulance_vehicle") 

                # Dynamic Cross-Traffic Sensor
                if cross_car is not None:  
                    audi_light = cross_car.get_traffic_light()
                    if audi_light is not None and audi_light.get_state() != carla.TrafficLightState.Green:
                        audi_light.set_state(carla.TrafficLightState.Green)
                        audi_light.freeze(True)
                    
                    cross_loc = cross_car.get_location()
                    cross_dist = math.hypot(cross_loc.x - car_loc.x, cross_loc.y - car_loc.y)
                    
                    # THE FIX: Is the Audi moving towards us or away from us?
                    cross_fwd = cross_car.get_transform().get_forward_vector()
                    to_ego_x = car_loc.x - cross_loc.x
                    to_ego_y = car_loc.y - cross_loc.y
                    
                    # Dot product > 0 means Audi hasn't crossed our path yet
                    # Dot product < 0 means Audi has crossed and is driving away
                    is_approaching = (cross_fwd.x * to_ego_x) + (cross_fwd.y * to_ego_y) > 0
                    
                    # Only trigger if within 45m AND still approaching the intersection
                    if cross_dist < 30.0 and is_approaching:
                        live_facts.append("traffic")

                # Logic Engine Evaluation
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
                
                start_time = time.perf_counter()
                clingo_output = str(logic_engine.evaluate(facts_header + rules_block))
                inference_ms = (time.perf_counter() - start_time) * 1000
                inference_log.append(inference_ms)

                sys.stdout.write(f"\rFacts: {live_facts} | Output: {clingo_output}   ")
                sys.stdout.flush()

                # Dynamic Actuation
                if "non(enter_intersection)" in clingo_output:
                    # Trapped or Unsafe: Slam brakes, hold position.
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    
                elif "enter_intersection" in clingo_output:
                    # Release the ambulance to blow past us
                    if not ambulance_released and ambulance is not None:
                        tm.ignore_lights_percentage(ambulance, 100)
                        tm.ignore_vehicles_percentage(ambulance, 100) 
                        tm.vehicle_percentage_speed_difference(ambulance, -100.0) 
                        ambulance_released = True

                    # THE FIX: Calculate physical displacement
                    dist_moved = math.hypot(car_loc.x - maneuver_start_loc.x, car_loc.y - maneuver_start_loc.y)
                    
                    if dist_moved < 6.0:
                        # We haven't moved far enough yet. Keep pulling over aggressively.
                        ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                        ego_vehicle.apply_control(carla.VehicleControl(throttle=0.75, steer=0.20, brake=0.0))
                    else:
                        # We have moved 6 meters into the intersection. We are safely out of the way. 
                        # YIELD: Hold the brakes and wait for the ambulance.
                        ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                        ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0))

                # Dynamic Exit Condition: Check if the Ambulance has successfully passed us
                to_amb_x = amb_loc.x - car_loc.x
                to_amb_y = amb_loc.y - car_loc.y
                amb_dot_product = (car_fwd.x * to_amb_x) + (car_fwd.y * to_amb_y)
                
                # If dot product is > 0, the ambulance is physically in front of our bumper
                if amb_dot_product > 0 and amb_dist > 5.0:
                    print(f"\n\n✅ AMBULANCE PASSED SAFELY. Maneuver complete.")
                    avg_latency = sum(inference_log) / len(inference_log) if inference_log else 0.0
                    
                    # Lock brakes to end trial cleanly
                    ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, throttle=0.0, steer=0.0))
                    time.sleep(1.0)
                    return f"PASS - Avg Latency: {avg_latency:.2f}ms"
                    
            # 20Hz Loop
            time.sleep(0.05)
            
    except Exception as e:
        print(f"\n❌ Trial Crashed: {e}")
        return "FAIL (CRASH)"
        
    finally:
        print(f"\n🧹 Cleaning up environment...")
        for actor in actor_list:
            if actor is not None and actor.is_alive:
                if 'vehicle' in actor.type_id:
                    try: actor.set_autopilot(False)
                    except: pass 
        for actor in actor_list:
            if actor is not None and actor.is_alive:
                actor.destroy()
        time.sleep(1.0)

def main():
    print("🔌 Connecting to CARLA...")
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    
    print("🌍 Loading Town07 (Rural Environment)...")
    world = client.load_world('Town07')
    tm = client.get_trafficmanager(8000)

    traffic_lights = world.get_actors().filter('traffic.traffic_light')
    for tl in traffic_lights:
        tl.set_state(carla.TrafficLightState.Red)
        tl.freeze(True)
    print("🛑 All traffic lights locked to RED.")
    
    blueprint_library = world.get_blueprint_library()
    root_folder = r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic"
    logic_engine = DDLEngine(root_folder)

    # Run the trial exactly once
    result = run_trial(client, world, tm, blueprint_library, logic_engine)
    
    print("\n\n" + "="*60)
    print("📊 FINAL SCENARIO RESULT")
    print("="*60)
    print(f"Outcome: {result}")
    print("="*60)

if __name__ == '__main__':
    main()