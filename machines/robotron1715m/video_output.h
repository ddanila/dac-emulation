#ifndef DAC_ROBOTRON_VIDEO_OUTPUT_H
#define DAC_ROBOTRON_VIDEO_OUTPUT_H
#include "robotron.h"
/* Common clock: CPU=45 ticks, dot=13 ticks, character=104 ticks.
 * Separate observer state: never serialized in, or written into, robotron. */
#define ROBOTRON_VIDEO_HZ 179712000u
#define ROBOTRON_VIDEO_PULSE 1060u /* 5.89866 us; drawing says nominal 5.9 us. */
typedef void (*robotron_video_sink)(void *, uint64_t, unsigned, unsigned, unsigned);
typedef struct {
  uint64_t time, uv1_end, uv2_end;
  unsigned word, highlight, hrtc, vrtc, vertical, delay, levels, initialized;
  unsigned phase, dot;
  robotron_video_sink sink;
  void *user;
} robotron_video_output;
void robotron_video_output_init(robotron_video_output *, const robotron *, robotron_video_sink, void *);
void robotron_video_output_run(robotron *, robotron_video_output *, unsigned);
/* Logic primitive is also used for independent schematic-vector tests. */
void robotron_video_output_logic(robotron_video_output *, uint64_t, unsigned, unsigned, unsigned, unsigned);
#endif
