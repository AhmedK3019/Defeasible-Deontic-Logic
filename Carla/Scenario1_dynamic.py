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
    actor_list = []

    # Initialize the Logic Engine ONCE
    root_folder = r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic"
    logic_engine = DDLEngine(root_folder)

    try:
        # 1. Spawn Ego Vehicle
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100')
        spawn_points = world.get_map().get_spawn_points()

        car_spawn = spawn_points[55]
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned")

        initial_lane_id = world.get_map().get_waypoint(car_spawn.location).lane_id

        # Static Camera Setup
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 8)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 8)
        cam_z = car_transform.location.z + 3.0
        spectator.set_transform(carla.Transform(carla.Location(x=cam_x, y=cam_y, z=cam_z), car_transform.rotation))

        # 2. Spawn Hazard (20 meters ahead)
        object_bp = blueprint_library.find('static.prop.barrel')
        forward_vector = car_spawn.get_forward_vector()
        obj_x = car_spawn.location.x + (forward_vector.x * 20.0)
        obj_y = car_spawn.location.y + (forward_vector.y * 20.0)
        object_loc = carla.Location(x=obj_x, y=obj_y, z=car_spawn.location.z)
        object = world.spawn_actor(object_bp, spawn_points[13])
        actor_list.append(object)
        print("✅ Object Spawned")

        # 3. Spawn Oncoming Cars (A Convoy of Two)
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200')
        
        oncoming_cars = []
        forward_vector = car_spawn.get_forward_vector()
        right_vector = car_spawn.get_right_vector()
        
        # Car 1: The Decoy (45 meters ahead)
        audi1_x = car_spawn.location.x + (forward_vector.x * 45.0) + (right_vector.x * -3.5)
        audi1_y = car_spawn.location.y + (forward_vector.y * 45.0) + (right_vector.y * -3.5)
        audi_rot = car_spawn.rotation
        audi_rot.yaw += 180.0 
        
        # audi1 = world.spawn_actor(audi_bp, carla.Transform(carla.Location(x=audi1_x, y=audi1_y, z=car_spawn.location.z + 2.0), audi_rot))
        # actor_list.append(audi1)
        # oncoming_cars.append(audi1)

        # Car 2: The Surprise (75 meters ahead)
        audi2_x = car_spawn.location.x + (forward_vector.x * 85.0) + (right_vector.x * -3.5)
        audi2_y = car_spawn.location.y + (forward_vector.y * 85.0) + (right_vector.y * -3.5)
        
        # audi2 = world.spawn_actor(audi_bp, carla.Transform(carla.Location(x=audi2_x, y=audi2_y, z=car_spawn.location.z + 2.0), audi_rot))
        # actor_list.append(audi2)
        # oncoming_cars.append(audi2)
        
        print("✅ Convoy of 2 Oncoming Cars Spawned")
        for car in oncoming_cars:
            car.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0))

        # Initial Acceleration
        ego_vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0))
        print("🚗 Vehicle in motion... Engaging Dynamic Logic Engine")

        current_steer = 0.0
        throttle_integral = 0.0
        target_speed_mps = 8.0
        has_seen_obstacle = False

        # 4. THE DYNAMIC PERCEPTION & CONTROL LOOP (20 Hz)
        while True:
            car_loc = ego_vehicle.get_location()
            obj_loc = object.get_location()
            
            # --- DIRECTIONAL SPATIAL MATH ---
            to_obj_x = obj_loc.x - car_loc.x
            to_obj_y = obj_loc.y - car_loc.y
            distance_to_hazard = math.hypot(to_obj_x, to_obj_y)
            
            car_fwd = ego_vehicle.get_transform().get_forward_vector()
            obj_dot = (car_fwd.x * to_obj_x) + (car_fwd.y * to_obj_y)

            waypoint = world.get_map().get_waypoint(car_loc)
            lane_center_dist = math.hypot(car_loc.x - waypoint.transform.location.x, 
                                          car_loc.y - waypoint.transform.location.y)

            sys.stdout.write(f"\rDistance to hazard: {distance_to_hazard:.2f}m | Off-center: {lane_center_dist:.2f}m   ")
            sys.stdout.flush()

            # --- DYNAMIC KINEMATIC THRESHOLD & MEMORY ---
            velocity = ego_vehicle.get_velocity()
            speed = math.hypot(velocity.x, velocity.y)
            dynamic_obstacle_threshold = 3.0 + (speed * 1.5) 
            
            if distance_to_hazard < dynamic_obstacle_threshold and obj_dot > 0:
                has_seen_obstacle = True
            elif obj_dot < -2.0:
                has_seen_obstacle = False # Barrel is behind us, forget it

            # --- FACT GENERATION ---
            live_facts = ["driving"]
            
            if waypoint.left_lane_marking.type == carla.LaneMarkingType.Solid:
                live_facts.append("solid_line")
            else:
                live_facts.append("dashed_line") 

            if has_seen_obstacle:
                live_facts.append("obstacle")
                live_facts.append("short_distance")

            # --- DYNAMIC SENSOR: Directional Oncoming Traffic (Array Scan) ---
            threat_detected = False
            
            for o_car in oncoming_cars:
                if o_car is not None and o_car.is_alive:
                    o_loc = o_car.get_location()
                    o_dist = math.hypot(o_loc.x - car_loc.x, o_loc.y - car_loc.y)
                    
                    # Vector math to check if the specific car is IN FRONT of us
                    to_target_x = o_loc.x - car_loc.x
                    to_target_y = o_loc.y - car_loc.y
                    dot_product = (car_fwd.x * to_target_x) + (car_fwd.y * to_target_y)
                    
                    if o_dist < 30.0 and dot_product > 0:
                        threat_detected = True
                        break # One threat is enough to trigger the rule
                        
            if threat_detected:
                live_facts.append("oncoming_traffic")

            # --- LOGIC EVALUATION ---
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
            
            clingo_output = logic_engine.evaluate(facts_header + rules_block)

            current_lane_id = waypoint.lane_id
            print(f"\nInit Lane: {initial_lane_id} | Curr Lane: {current_lane_id} | Facts: {live_facts} | Clingo: {clingo_output}")

            # --- DYNAMIC ACTUATION (PURE GEOMETRY PD CONTROLLER) ---
            current_wp = world.get_map().get_waypoint(car_loc)
            
            # 1. Are we physically in a lane facing backwards?
            wp_fwd = current_wp.transform.get_forward_vector()
            in_oncoming_lane = ((car_fwd.x * wp_fwd.x) + (car_fwd.y * wp_fwd.y)) < 0.0

            # 2. Logic to Target Waypoint (Completely ignoring Lane IDs)
            target_wp = current_wp
            
            # CATCH THE NEGATIVE LOGIC FIRST
            if "non(cross_line)" in clingo_output:
                if "obstacle" not in live_facts:
                    ego_vehicle.set_light_state(carla.VehicleLightState.NONE)
                
                if in_oncoming_lane:
                    # RECOVERY: We are in the oncoming lane, find the forward-facing lane to return to
                    ego_vehicle.set_light_state(carla.VehicleLightState.RightBlinker)
                    for l in [current_wp.get_left_lane(), current_wp.get_right_lane()]:
                        if l is not None:
                            l_fwd = l.transform.get_forward_vector()
                            if ((car_fwd.x * l_fwd.x) + (car_fwd.y * l_fwd.y)) > 0:
                                target_wp = l
                                break
                    
            elif "cross_line" in clingo_output:
                ego_vehicle.set_light_state(carla.VehicleLightState.LeftBlinker)
                
                if not in_oncoming_lane:
                    # EVASION: We are in the forward lane, find the backward-facing lane to evade into
                    for l in [current_wp.get_left_lane(), current_wp.get_right_lane()]:
                        if l is not None:
                            l_fwd = l.transform.get_forward_vector()
                            if ((car_fwd.x * l_fwd.x) + (car_fwd.y * l_fwd.y)) < 0:
                                target_wp = l
                                break

            # 3. Calculate Geometry Errors
            target_fwd = target_wp.transform.get_forward_vector()
            
            # Does our chosen target lane face backward? 
            target_is_backward = ((car_fwd.x * target_fwd.x) + (car_fwd.y * target_fwd.y)) < 0.0

            dx = car_loc.x - target_wp.transform.location.x
            dy = car_loc.y - target_wp.transform.location.y
            right_vec = target_wp.transform.get_right_vector()
            cte = (dx * right_vec.x) + (dy * right_vec.y)

            car_yaw = ego_vehicle.get_transform().rotation.yaw
            road_yaw = target_wp.transform.rotation.yaw
            
            # CRUCIAL FIX: Flip perspective based on the TARGET, not our current physical location
            if target_is_backward:
                road_yaw = (road_yaw + 180) % 360
                cte = -cte 
                
            yaw_diff = (car_yaw - road_yaw + 180) % 360 - 180

            # 4. PD Controller Math for Steering
            steer_target = (-0.20 * cte) + (-0.02 * yaw_diff) 
            steer_target = max(min(steer_target, 0.6), -0.6) 
            current_steer = current_steer + 0.3 * (steer_target - current_steer)

            # --- 5. LONGITUDINAL PID CONTROLLER (Auto-Speed) ---
            speed_error = target_speed_mps - speed
            throttle_integral += speed_error * 0.05
            throttle_integral = max(min(throttle_integral, 1.0), 0.0) # Anti-windup
            
            calc_throttle = (0.15 * speed_error) + (0.05 * throttle_integral)
            calc_throttle = max(min(calc_throttle, 0.8), 0.0)

            # Update dashboard so you can watch the math live
            sys.stdout.write(f"\rTgtBack: {target_is_backward} | CTE: {cte: .2f} | YawDiff: {yaw_diff: .0f}° | Steer: {steer_target: .2f}   ")
            sys.stdout.flush()

            # 6. Resolve Control
            if "non(cross_line)" in clingo_output and "obstacle" in live_facts:
                ego_vehicle.set_light_state(carla.VehicleLightState.Brake)
                ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0))
            elif clingo_output.strip() == "":
                ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0))
            else:
                ego_vehicle.apply_control(carla.VehicleControl(throttle=calc_throttle, steer=current_steer, brake=0.0))
            
            # Maintain 20Hz loop
            time.sleep(0.05) 

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