from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ValueTrackingSlider(QSlider):
    def paintEvent(self, event):
        # 1. Draw the standard slider first
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 2. Get the handle's bounding box
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )

        # 3. Calculate text geometry
        value_text = str(self.value())
        font_metrics = painter.fontMetrics()
        text_width = font_metrics.horizontalAdvance(value_text)

        # 4. Center the text horizontally relative to the handle center
        target_x = handle_rect.center().x() - (text_width // 2)

        # 5. LEFT BOUNDARY LOGIC
        # If the left edge of the text goes below 2px, pin it to 2px
        if target_x < 2:
            target_x = 2

        # 6. RIGHT BOUNDARY LOGIC
        # If the right edge of the text exceeds widget width, pin it to the edge
        right_limit = self.width() - text_width - 2
        if target_x > right_limit:
            target_x = right_limit

        # 7. Draw the text
        # Y position is roughly 8px above the handle
        text_pos = QPoint(
            target_x,
            handle_rect.top() - 8,
        )

        painter.drawText(text_pos, value_text)
        painter.end()
