'use client';

import { useCallback } from 'react';
import { useTheme } from 'next-themes';
import { AnimatePresence, motion } from 'motion/react';
import { toast } from 'sonner';
import { useAgent, useSessionContext } from '@livekit/components-react';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { WelcomeView } from '@/components/app/welcome-view';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(AgentSessionView_01);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
    },
    hidden: {
      opacity: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.5,
    ease: 'linear',
  },
};

interface ViewControllerProps {
  isVideoInputSupported: boolean;
}

export function ViewController({ isVideoInputSupported }: ViewControllerProps) {
  const { isConnected, start } = useSessionContext();
  const agent = useAgent();
  const { resolvedTheme } = useTheme();

  const handleStartCall = useCallback(async () => {
    try {
      await start({
        roomConnectOptions: {
          // The SDK default is 15s for the signal websocket. On a slow or
          // lossy link the TLS handshake alone can take longer than that, and
          // the connect fails before it was ever given a chance.
          websocketTimeout: 30_000,
        },
      });
    } catch (error) {
      // Never leave this rejection unhandled: in development Next renders it
      // as a full-page error overlay instead of anything the user can act on.
      console.error(error);
      toast.error('Could not connect to LiveKit', {
        description: 'The connection timed out. Check your network and try again.',
      });
    }
  }, [start]);

  return (
    <AnimatePresence mode="wait">
      {/* Welcome view */}
      {!isConnected && (
        <MotionWelcomeView
          key="welcome"
          {...VIEW_MOTION_PROPS}
          startButtonText="Start call"
          onStartCall={handleStartCall}
        />
      )}
      {/* Session view */}
      {isConnected && (
        <MotionSessionView
          key="session-view"
          {...VIEW_MOTION_PROPS}
          preConnectMessage={
            agent.isConnected ? 'Agent is listening, ask it a question' : 'Waiting for agent'
          }
          supportsChatInput={true}
          supportsVideoInput={isVideoInputSupported}
          supportsScreenShare={isVideoInputSupported}
          isPreConnectBufferEnabled={true}
          audioVisualizerType="aura"
          themeMode={resolvedTheme === 'dark' ? 'dark' : 'light'}
          className="fixed inset-0"
        />
      )}
    </AnimatePresence>
  );
}
