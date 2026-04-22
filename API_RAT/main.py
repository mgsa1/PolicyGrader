"""API_RAT — a rat tries to steal the ANTHROPIC_API_KEY box from under a
broom-wielding Franka Panda. First-person from the rat.

Run with:
    # macOS (required by mujoco.viewer.launch_passive on darwin)
    .venv/bin/mjpython -m API_RAT.main

    # linux
    python -m API_RAT.main
"""

from __future__ import annotations

import math
import secrets
import time
import traceback
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

from API_RAT.rat_controller import RatController
from API_RAT.robot_controller import RobotController

SCENE_PATH = Path(__file__).parent / "scene.xml"
VICTORY_RADIUS = 0.22
ROOM_HALF = 7.8

# Intro sequence: hold third-person "this is your rat" shot before handing
# control to the player. Long enough to notice whiskers + ears + tail.
INTRO_DURATION = 3.5

# Broom contacts scale the rat's per-step velocity change 3× (1× natural
# + 2× extra) so the fling feels like a smash instead of a nudge.
PUSHBACK_BOOST = 2.0


def claim_code() -> str:
    return "RAT-" + secrets.token_hex(3).upper()


def main() -> None:
    model = mujoco.MjModel.from_xml_path(str(SCENE_PATH))
    data = mujoco.MjData(model)

    start_key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "start")
    mujoco.mj_resetDataKeyframe(model, data, start_key)
    data.ctrl[:] = model.key_ctrl[start_key]

    hand_body = model.body("hand").id
    broom_body = model.body("broom").id
    key_box_body = model.body("ANTHROPIC_API_KEY").id
    rat_cam_id = model.camera("rat_cam").id
    intro_cam_id = model.camera("intro_cam").id
    broom_mocap_id = int(model.body_mocapid[broom_body])

    mujoco.mj_forward(model, data)
    data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
    data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]

    rat = RatController(model, data)
    robot = RobotController(model, data)

    key_box_pos = np.array(data.xpos[key_box_body], copy=True)

    # Precompute the set of broom geom ids so the per-step contact scan
    # stays tight.
    broom_geom_ids = {
        model.geom("broom_handle").id,
        model.geom("broom_bristles").id,
    }

    def broom_is_touching_rat() -> bool:
        for c_idx in range(data.ncon):
            con = data.contact[c_idx]
            g1, g2 = int(con.geom1), int(con.geom2)
            if g1 in broom_geom_ids and int(model.geom_bodyid[g2]) == rat.rat_body_id:
                return True
            if g2 in broom_geom_ids and int(model.geom_bodyid[g1]) == rat.rat_body_id:
                return True
        return False

    state = {
        "won": False,
        "code": "",
        "reset_requested": False,
        "win_time": 0.0,
        "intro_start": 0.0,
        "intro_active": True,
        "intro_announced": False,
    }

    def request_reset() -> None:
        mujoco.mj_resetDataKeyframe(model, data, start_key)
        data.ctrl[:] = model.key_ctrl[start_key]
        mujoco.mj_forward(model, data)
        data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
        data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]
        rat.clear_input()
        robot.reaction_timer = 0.0
        robot.lunge_state = "idle"
        robot.lunge_cooldown = 0.0
        state["won"] = False
        state["code"] = ""
        state["intro_start"] = time.perf_counter()
        state["intro_active"] = True
        state["intro_announced"] = False

    def key_callback(key: int) -> None:
        import glfw

        if key == glfw.KEY_R:
            state["reset_requested"] = True
            return
        # Ignore movement keys during the intro reveal.
        if state["intro_active"]:
            return
        rat.on_key(key)

    try:
        with mujoco.viewer.launch_passive(
            model,
            data,
            key_callback=key_callback,
            show_left_ui=False,
            show_right_ui=False,
        ) as viewer:
            viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
            viewer.cam.fixedcamid = intro_cam_id
            # Rendering cost controls: no per-body text labels (those render
            # 3D text for every body every frame), no debug visualizations.
            viewer.opt.label = mujoco.mjtLabel.mjLABEL_NONE
            for flag in (
                mujoco.mjtVisFlag.mjVIS_INERTIA,
                mujoco.mjtVisFlag.mjVIS_JOINT,
                mujoco.mjtVisFlag.mjVIS_ACTUATOR,
                mujoco.mjtVisFlag.mjVIS_CONTACTPOINT,
                mujoco.mjtVisFlag.mjVIS_CONTACTFORCE,
                mujoco.mjtVisFlag.mjVIS_TRANSPARENT,
                mujoco.mjtVisFlag.mjVIS_AUTOCONNECT,
                mujoco.mjtVisFlag.mjVIS_COM,
                mujoco.mjtVisFlag.mjVIS_PERTFORCE,
                mujoco.mjtVisFlag.mjVIS_PERTOBJ,
            ):
                viewer.opt.flags[flag] = 0
            # Hide collision-only geoms (Franka collision meshes are group 3)
            # and any ancillary groups. Visuals live in group 0-2.
            for g in range(3, 6):
                viewer.opt.geomgroup[g] = 0

            sim_dt = model.opt.timestep
            frame_dt = 1.0 / 60.0
            last_real = time.perf_counter()
            sim_accum = 0.0
            last_print = 0.0
            frame_counter = [0]
            state["intro_start"] = last_real

            print_banner()

            # Cap the per-frame sim catch-up to 2 render frames. Without
            # this, a single slow frame can make the inner sim loop spiral:
            # more steps -> slower frame -> even more steps.
            MAX_SIM_PER_FRAME = 2.5 * frame_dt

            while viewer.is_running():
                now = time.perf_counter()
                sim_accum = min(sim_accum + (now - last_real), MAX_SIM_PER_FRAME)
                last_real = now

                # Intro → FPV transition.
                if state["intro_active"]:
                    elapsed_intro = now - state["intro_start"]
                    if not state["intro_announced"]:
                        print(
                            f"  ↳ meet the rat. controls unlock in {INTRO_DURATION:.1f}s…",
                            flush=True,
                        )
                        state["intro_announced"] = True
                    if elapsed_intro >= INTRO_DURATION:
                        state["intro_active"] = False
                        viewer.cam.fixedcamid = rat_cam_id
                        print("  ↳ now you. good luck.", flush=True)

                if state["reset_requested"]:
                    request_reset()
                    state["reset_requested"] = False
                    viewer.cam.fixedcamid = intro_cam_id
                    continue

                steps_this_frame = 0
                while sim_accum >= sim_dt and steps_this_frame < 10:
                    if state["intro_active"] or state["won"]:
                        data.ctrl[rat.act_fx] = 0.0
                        data.ctrl[rat.act_fy] = 0.0
                        data.ctrl[rat.act_vyaw] = 0.0
                        if not state["won"]:
                            robot.step(sim_dt)
                    else:
                        rat.step()
                        robot.step(sim_dt)
                    data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
                    data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]

                    # Cache pre-step rat velocity + whether the broom is
                    # touching it, so we can amplify the contact-induced
                    # delta-v after mj_step.
                    boost_active = broom_is_touching_rat()
                    if boost_active:
                        pre_vx = float(data.qvel[rat.dofadr_x])
                        pre_vy = float(data.qvel[rat.dofadr_y])

                    mujoco.mj_step(model, data)

                    if boost_active:
                        actuator_dv_x = float(data.ctrl[rat.act_fx]) * sim_dt / rat.m_eff
                        actuator_dv_y = float(data.ctrl[rat.act_fy]) * sim_dt / rat.m_eff
                        dv_x = float(data.qvel[rat.dofadr_x]) - pre_vx
                        dv_y = float(data.qvel[rat.dofadr_y]) - pre_vy
                        # Contact-induced delta-v = total dv minus what the
                        # actuator would have added in an empty step.
                        contact_dv_x = dv_x - actuator_dv_x
                        contact_dv_y = dv_y - actuator_dv_y
                        data.qvel[rat.dofadr_x] += PUSHBACK_BOOST * contact_dv_x
                        data.qvel[rat.dofadr_y] += PUSHBACK_BOOST * contact_dv_y

                    sim_accum -= sim_dt
                    steps_this_frame += 1

                if not state["won"] and not state["intro_active"]:
                    rp = data.xpos[rat.rat_body_id]
                    dx = float(rp[0]) - float(key_box_pos[0])
                    dy = float(rp[1]) - float(key_box_pos[1])
                    if math.hypot(dx, dy) < VICTORY_RADIUS:
                        state["won"] = True
                        state["code"] = claim_code()
                        state["win_time"] = time.perf_counter()
                        print()
                        print("=" * 52)
                        print("  YOU GOT PAST THE BROOM.")
                        print("  Email gallet_matthieu@hotmail.fr with this code")
                        print(f"  to claim your prepaid API key:   {state['code']}")
                        print("  Press R to play again, close window to quit.")
                        print("=" * 52)

                viewer.sync()

                elapsed_frame = time.perf_counter() - now
                if elapsed_frame < frame_dt:
                    time.sleep(frame_dt - elapsed_frame)

                frame_counter[0] += 1
                if now - last_print > 2.0:
                    rp = data.xpos[rat.rat_body_id]
                    d_box = math.hypot(
                        float(rp[0]) - float(key_box_pos[0]),
                        float(rp[1]) - float(key_box_pos[1]),
                    )
                    if state["won"]:
                        status = "WON  "
                    elif state["intro_active"]:
                        status = "intro"
                    else:
                        status = "alive"
                    dt_print = now - last_print
                    fps = frame_counter[0] / dt_print if dt_print > 0 else 0.0
                    print(
                        f"[{status}] rat=({rp[0]:+.2f},{rp[1]:+.2f})  "
                        f"dist_to_box={d_box:.2f}  "
                        f"lunge={robot.lunge_state}  "
                        f"fps={fps:.0f}",
                        flush=True,
                    )
                    last_print = now
                    frame_counter[0] = 0

        print("  ↳ viewer closed. see you.", flush=True)
    except Exception:
        print("  ↳ API_RAT crashed — traceback follows", flush=True)
        traceback.print_exc()
        raise


def print_banner() -> None:
    print()
    print("=" * 52)
    print("  API_RAT")
    print("  You are the rat. Steal the ANTHROPIC_API_KEY box.")
    print("  W/S or ↑/↓ move  |  A/D or ←/→ turn  |  Q/E strafe  |  R reset")
    print("  Floor is ice. Broom is fast. Good luck.")
    print("=" * 52)
    print()


if __name__ == "__main__":
    main()
