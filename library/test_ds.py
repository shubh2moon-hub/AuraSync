"""Quick test rebuild for demon_slayer only."""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'library'))
os.chdir(os.path.dirname(__file__) + '/..')

exec(open('library/rebuild_improved.py').read().replace("if __name__ == '__main__':", "if False:"))

# Just rebuild demon_slayer
land_bgr = cv2.imread('library/packs/demon_slayer/phone_land_base.jpg')
port_bgr = cv2.imread('library/packs/demon_slayer/phone_base.jpg')
land_rgb = cv2.cvtColor(land_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
port_rgb = cv2.cvtColor(port_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
assemble_pack('demon_slayer','Demon Slayer: Neo Tokyo','Tanjiro','#00ff9d',land_rgb,port_rgb,mask_fn=mask_demon_slayer)

ADIR = r'C:\Users\shubh\.gemini\antigravity\brain\797c4c8d-6575-4c9e-984f-0ca038f793dc'
base = cv2.imread('library/packs/demon_slayer/phone_base.jpg')
light = cv2.imread('library/packs/demon_slayer/phone_light.jpg', cv2.IMREAD_GRAYSCALE)
pw,ph = 360,800
base = cv2.resize(base,(pw,ph)); light = cv2.resize(light,(pw,ph))
base_f = cv2.cvtColor(base, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
light_f = light.astype(np.float32)/255.0
col = np.array([0.0,1.0,0.616],np.float32)
comp = np.clip(base_f + light_f[...,None]*col*0.80 + (light_f[...,None]**2)*0.20,0,1)
cv2.imwrite(f'{ADIR}/sim_ds_v3b.png', cv2.cvtColor((comp*255).astype(np.uint8),cv2.COLOR_RGB2BGR))
print('Done sim_ds_v3b.png')
