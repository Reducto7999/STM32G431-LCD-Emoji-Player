#ifndef __GIF_ANIMATION_H
#define __GIF_ANIMATION_H

#include "lcd.h"

#define GIF_FRAME_WIDTH   240
#define GIF_FRAME_HEIGHT  240
#define GIF_FRAME_COUNT   28
#define GIF_MAX_COLORS    16
#define GIF_FRAME_DELAY_MS 0

void GIF_ShowFrame(u8 frameIndex);
void GIF_ShowNextFrame(void);

#endif /* __GIF_ANIMATION_H */
