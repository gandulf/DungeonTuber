import { api } from '../api';
import type { Light } from '../types';
import { errorToast } from './ui.svelte';

export const lights = $state({
  enabled: true,
  list: [] as Light[],
  scenes: [] as string[],
  selected: [] as string[], // macs
  discovering: false,
});

export async function loadLights() {
  const result = await api.lights();
  lights.enabled = result.enabled;
  lights.list = result.lights;
  lights.scenes = result.scenes;
}

export async function discoverLights() {
  lights.discovering = true;
  try {
    const result = await api.discoverLights();
    lights.list = result.lights;
    lights.scenes = result.scenes;
    if (!lights.selected.length && result.lights.length) lights.selected = [result.lights[0].mac];
  } catch (e) {
    errorToast(e);
  } finally {
    lights.discovering = false;
  }
}

export function setLightState(list: Light[]) {
  lights.list = list;
}

/** Applies a change to every selected light. */
export async function patchSelected(patch: Partial<Light> & { clear_color?: boolean }) {
  const macs = lights.selected.length ? lights.selected : [];
  for (const mac of macs) {
    try {
      const updated = await api.patchLight(mac, patch);
      const index = lights.list.findIndex((light) => light.mac === mac);
      if (index >= 0) lights.list[index] = updated;
    } catch (e) {
      errorToast(e);
    }
  }
}

export async function renameLight(mac: string, name: string) {
  try {
    const updated = await api.patchLight(mac, { name });
    const index = lights.list.findIndex((light) => light.mac === mac);
    if (index >= 0) lights.list[index] = updated;
  } catch (e) {
    errorToast(e);
  }
}
