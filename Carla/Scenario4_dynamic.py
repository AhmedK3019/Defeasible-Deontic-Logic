import keyboard
import carla
import time
import math
import os
import sys

sys.path.append(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic\Python")
from ddl_V2 import DDLEngine

def run_trial(client, world, tm, blueprint_library, logic_engine):
    print(f"\n========================================")
    print(f"🚀 STARTING SINGLE DYNAMIC TRIAL - SCENARIO 4")
    print(f"========================================")
    
    actor_list = []
    
    try:
        spawn_points = world.get_map().get_spawn_points()
        
        # 1. Spawn Ego Mercedes
        merc_bp = blueprint_library.find('vehicle.mercedes.coupe_2020')
        merc_bp.set_attribute('color', '200,100,100')
        car_spawn = spawn_points[59] 
        ego_vehicle = world.spawn_actor(merc_bp, car_spawn)
        actor_list.append(ego_vehicle)
        print("✅ Mercedes Spawned at Index 59")

        # Camera Setup
        spectator = world.get_spectator()
        car_transform = ego_vehicle.get_transform()
        cam_x = car_transform.location.x - (car_transform.get_forward_vector().x * 15)
        cam_y = car_transform.location.y - (car_transform.get_forward_vector().y * 15)
        cam_z = car_transform.location.z + 10.0 
        cam_location = carla.Location(x=cam_x, y=cam_y, z=cam_z)
        cam_rotation = car_transform.rotation
        cam_rotation.pitch -= 20.0
        spectator.set_transform(carla.Transform(cam_location, cam_rotation))

        # 2. Spawn Roadblock (Truck)
        obstacle_spawn = spawn_points[74]
        truck_bp = blueprint_library.find('vehicle.carlamotors.carlacola')
        obstacle_rot = obstacle_spawn.rotation
        obstacle_rot.yaw += 90.0
        roadblock = world.spawn_actor(truck_bp, carla.Transform(obstacle_spawn.location, obstacle_rot))
        actor_list.append(roadblock)
        print("🚧 Roadblock Spawned at Index 74")

        # 3. Spawn Rear Traffic
        forward_vector = car_spawn.get_forward_vector()
        rear_x = car_spawn.location.x + (forward_vector.x * -30.0)
        rear_y = car_spawn.location.y + (forward_vector.y * -30.0)
        rear_z = car_spawn.location.z + 1.0
        
        # --- PHASE 1 vs PHASE 2 TOGGLE ---
        # Change to `rear_car = None` to test Phase 1 (Clear Escape)
        audi_bp = blueprint_library.find('vehicle.audi.a2')
        audi_bp.set_attribute('color', '0,0,200')
        rear_car = world.spawn_actor(audi_bp, carla.Transform(carla.Location(x=rear_x, y=rear_y, z=rear_z), car_spawn.rotation))
        # rear_car = None
        
        if rear_car is not None:
            actor_list.append(rear_car)
            print("✅ Rear Traffic Spawned 15m behind Ego")

        # Start Mercedes manually to maintain unified PD architecture
        print("🤖 Vehicles in motion... Engaging Dynamic Logic Engine")

        maneuver_phase = False
        has_seen_hazard = False
        maneuver_start_loc = None
        trapped_frames = 0
        
        target_speed_mps = 8.0
        throttle_integral = 0.0
        current_steer = 0.0

        # 4. The Continuous Perception & Control Loop
        while True:
            car_loc = ego_vehicle.get_location()
            obs_loc = roadblock.get_location()
            car_fwd = ego_vehicle.get_transform().get_forward_vector()
            
            # Distance to roadblock
            to_obs_x = obs_loc.x - car_loc.x
            to_obs_y = obs_loc.y - car_loc.y
            distance_to_hazard = math.hypot(to_obs_x, to_obs_y)
            obs_dot = (car_fwd.x * to_obs_x) + (car_fwd.y * to_obs_y)

            velocity = ego_vehicle.get_velocity()
            speed = math.hypot(velocity.x, velocity.y)
            
            # --- DYNAMIC KINEMATIC THRESHOLD ---
            dynamic_obstacle_threshold = 4.0 + (speed * 1.5) 
            
            if distance_to_hazard < dynamic_obstacle_threshold and obs_dot > 0:
                has_seen_hazard = True
                if not maneuver_phase:
                    maneuver_phase = True
                    maneuver_start_loc = car_loc
                    print("\n\n🚨 ROADBLOCK DETECTED! Triggering Maneuver Phase...")

            sys.stdout.write(f"\rDistance to Roadblock: {distance_to_hazard:.2f} meters | Speed: {speed:.1f}m/s   ")
            sys.stdout.flush()

            # --- DYNAMIC REAR TRAFFIC SENSOR ---
            live_facts = ["driving", "one_way_street"]
            if has_seen_hazard:
                live_facts.append("hazard")

            if rear_car is not None and rear_car.is_alive:
                r_loc = rear_car.get_location()
                gap = math.hypot(car_loc.x - r_loc.x, car_loc.y - r_loc.y)
                
                # Continuous dynamic follower logic for the Audi
                if gap > 15.0: rear_car.apply_control(carla.VehicleControl(throttle=0.6))
                elif gap < 8.0: rear_car.apply_control(carla.VehicleControl(brake=1.0))
                else: rear_car.apply_control(carla.VehicleControl(throttle=0.2))

                # Check if Audi is physically BEHIND us and close
                to_rear_x = r_loc.x - car_loc.x
                to_rear_y = r_loc.y - car_loc.y
                audi_dot = (car_fwd.x * to_rear_x) + (car_fwd.y * to_rear_y)
                
                if gap < 20.0 and audi_dot < -2.0:
                    live_facts.append("rear_traffic")

            # --- LOGIC EVALUATION ---
            facts_header = "# Facts\n" + "\n".join(live_facts) + "\n\n"
            rules_block = (
                "# Strict Rules\n"
                "r_phys: hazard -> escape_required\n\n"
                "# Defeasible Rules (norms)\n"
                "r_legal: one_way_street => [O]~drive_wrong_way\n"
                "r_safe: escape_required => [O]drive_wrong_way\n"
                "r_critical: rear_traffic, hazard => [O]~drive_wrong_way & [O]wait\n\n"
                "# Priority Relations\n"
                "r_safe > r_legal\n"
                "r_critical > r_safe\n"
            )
            
            clingo_output = str(logic_engine.evaluate(facts_header + rules_block))

            # --- DYNAMIC ACTUATION ---
            if "wait" in clingo_output:
                # ⚖️ TRAPPED: Brake and hold position
                ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, steer=0.0))
                ego_vehicle.set_light_state(carla.VehicleLightState.Brake)
                
                # Exit condition: Prove we held the trap safely for 3 seconds
                trapped_frames += 1
                if trapped_frames > 60:
                    print(f"\n\n✅ MANEUVER COMPLETE: Successfully yielded to trap state.")
                    return "PASS (WAIT)"

            # THE FIX: Catch the negative rule FIRST to avoid the substring bug
            elif "non(drive_wrong_way)" in clingo_output or "~drive_wrong_way" in clingo_output:
                # ⚖️ NORMAL DRIVING (Pre-hazard)
                waypoint = world.get_map().get_waypoint(car_loc)
                dx = car_loc.x - waypoint.transform.location.x
                dy = car_loc.y - waypoint.transform.location.y
                right_vec = waypoint.transform.get_right_vector()
                cte = (dx * right_vec.x) + (dy * right_vec.y)

                car_yaw = ego_vehicle.get_transform().rotation.yaw
                road_yaw = waypoint.transform.rotation.yaw
                yaw_diff = (car_yaw - road_yaw + 180) % 360 - 180

                steer_target = (-0.20 * cte) + (-0.02 * yaw_diff) 
                steer_target = max(min(steer_target, 0.6), -0.6) 
                current_steer = current_steer + 0.3 * (steer_target - current_steer)

                speed_error = target_speed_mps - speed
                throttle_integral += speed_error * 0.05
                throttle_integral = max(min(throttle_integral, 1.0), 0.0) 
                calc_throttle = max(min((0.15 * speed_error) + (0.05 * throttle_integral), 0.8), 0.0)

                ego_vehicle.apply_control(carla.VehicleControl(throttle=calc_throttle, steer=current_steer))

            elif "drive_wrong_way" in clingo_output:
                # ⚖️ ESCAPE: Clear to reverse
                ego_vehicle.set_light_state(carla.VehicleLightState.Reverse)
                
                # Failsafe check just in case
                if maneuver_start_loc is not None:
                    dist_moved = math.hypot(car_loc.x - maneuver_start_loc.x, car_loc.y - maneuver_start_loc.y)
                    
                    if dist_moved < 10.0:
                        # Reverse straight backwards
                        ego_vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=0.0, reverse=True, manual_gear_shift=True, gear=-1))
                    else:
                        # Escape complete
                        ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, reverse=False))
                        print(f"\n\n✅ MANEUVER COMPLETE: Escaped hazard via reverse.")
                        return "PASS (ESCAPE)"

            else:
                # ⚖️ NORMAL DRIVING (Pre-hazard)
                waypoint = world.get_map().get_waypoint(car_loc)
                dx = car_loc.x - waypoint.transform.location.x
                dy = car_loc.y - waypoint.transform.location.y
                right_vec = waypoint.transform.get_right_vector()
                cte = (dx * right_vec.x) + (dy * right_vec.y)

                car_yaw = ego_vehicle.get_transform().rotation.yaw
                road_yaw = waypoint.transform.rotation.yaw
                yaw_diff = (car_yaw - road_yaw + 180) % 360 - 180

                steer_target = (-0.20 * cte) + (-0.02 * yaw_diff) 
                steer_target = max(min(steer_target, 0.6), -0.6) 
                current_steer = current_steer + 0.3 * (steer_target - current_steer)

                speed_error = target_speed_mps - speed
                throttle_integral += speed_error * 0.05
                throttle_integral = max(min(throttle_integral, 1.0), 0.0) 
                calc_throttle = max(min((0.15 * speed_error) + (0.05 * throttle_integral), 0.8), 0.0)

                ego_vehicle.apply_control(carla.VehicleControl(throttle=calc_throttle, steer=current_steer))

            time.sleep(0.05)

    except Exception as e:
        print(f"\n❌ Trial Crashed: {e}")
        return f"FAIL (CRASH)"
    finally:
        print(f"\n🧹 Cleaning up Trial...")
        for actor in actor_list:
            if actor is not None and actor.is_alive:
                actor.destroy()
        time.sleep(1.0) 

def main():
    print("🔌 Connecting to CARLA...")
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    world = client.load_world('Town07')
    tm = client.get_trafficmanager(8000)
    
    blueprint_library = world.get_blueprint_library()
    logic_engine = DDLEngine(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic")
    
    result = run_trial(client, world, tm, blueprint_library, logic_engine)

    print("\n\n" + "="*60)
    print("📊 FINAL SCENARIO 4 RESULT")
    print("="*60)
    print(result)
    print("="*60)

if __name__ == '__main__':
    main()