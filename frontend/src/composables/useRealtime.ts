/**
 * 实时数据组合函数
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { getRealtimeManager } from '../managers'
import type { ConnectionState } from '../types'

export function useRealtime() {
  const manager = getRealtimeManager()
  const connectionState = ref<ConnectionState>(manager.getConnectionState())
  const isConnected = ref(false)

  let unsubscribeState: (() => void) | null = null

  const subscribe = <T>(event: string, callback: (data: T) => void) => {
    return manager.subscribe(event, callback as (data: unknown) => void)
  }

  const connect = () => {
    manager.connect()
  }

  const disconnect = () => {
    manager.disconnect()
  }

  onMounted(() => {
    unsubscribeState = manager.onStateChange((state) => {
      connectionState.value = state
      isConnected.value = state.status === 'connected'
    })
    
    if (!manager.isConnected()) {
      manager.connect()
    }
  })

  onUnmounted(() => {
    if (unsubscribeState) {
      unsubscribeState()
    }
  })

  return {
    connectionState,
    isConnected,
    subscribe,
    connect,
    disconnect
  }
}
