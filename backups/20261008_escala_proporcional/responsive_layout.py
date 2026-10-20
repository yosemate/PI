"""Layouts que se ajustam em unidades lógicas do Qt, sem duplicar a escala DPI."""
from PyQt5.QtCore import Qt, QRect, QSize, QObject, QEvent
from PyQt5.QtWidgets import (QLayout, QWidget, QScrollArea, QVBoxLayout,
                             QDialog, QSizePolicy, QLabel)
import re

class FlowLayout(QLayout):
    """Distribui itens em linhas conforme o espaço e os tamanhos reais dos textos."""
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self.items=[]
        self.setSpacing(spacing)
    def addItem(self,item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self,index): return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index): return self.items.pop(index) if 0<=index<len(self.items) else None
    def addSpacing(self,size): pass
    def addStretch(self,stretch=0): pass
    def expandingDirections(self): return Qt.Orientations()
    def hasHeightForWidth(self): return True
    def heightForWidth(self,width): return self._arrange(QRect(0,0,width,0),True)
    def setGeometry(self,rect):
        super().setGeometry(rect)
        self._arrange(rect,False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        result=QSize()
        for item in self.items:
            if not item.isEmpty(): result=result.expandedTo(item.minimumSize())
        m=self.contentsMargins()
        return result+QSize(m.left()+m.right(),m.top()+m.bottom())
    def _arrange(self,rect,test):
        m=self.contentsMargins()
        available=rect.adjusted(m.left(),m.top(),-m.right(),-m.bottom())
        x,y=available.x(),available.y()
        row_height=0
        for item in self.items:
            if item.isEmpty(): continue
            hint=item.sizeHint().expandedTo(item.minimumSize())
            width=min(hint.width(),max(1,available.width()))
            if x>available.x() and x+width>available.x()+available.width():
                x=available.x(); y+=row_height+self.spacing(); row_height=0
            if not test: item.setGeometry(QRect(x,y,width,hint.height()))
            x+=width+self.spacing()
            row_height=max(row_height,hint.height())
        return y+row_height-rect.y()+m.bottom()

def adapt_labels(widget):
    """Textos longos quebram linha; valores numéricos permanecem em uma linha."""
    for label in widget.findChildren(QLabel):
        if len(label.text())>24:
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
            label.setMinimumWidth(0)

class DialogScreenAdapter(QObject):
    """Diálogos maiores que a tela ganham rolagem, mantendo todos os controles."""
    def eventFilter(self,obj,event):
        if isinstance(obj,QDialog) and event.type()==QEvent.Show and not obj.property("screenAdapted"):
            screen=obj.screen()
            if screen:
                area=screen.availableGeometry()
                max_w,max_h=max(240,area.width()-40),max(200,area.height()-60)
                requested=obj.size().expandedTo(obj.minimumSizeHint())
                if requested.width()>max_w or requested.height()>max_h:
                    old=obj.layout()
                    if old:
                        content=QWidget()
                        content.setLayout(old)
                        scroll=QScrollArea(obj)
                        scroll.setWidgetResizable(True)
                        scroll.setWidget(content)
                        scroll.setFrameShape(QScrollArea.NoFrame)
                        layout=QVBoxLayout(obj)
                        layout.setContentsMargins(0,0,0,0)
                        layout.addWidget(scroll)
                        obj.setMinimumSize(0,0)
                        obj.setMaximumSize(16777215,16777215)
                        obj.resize(min(requested.width(),max_w),min(requested.height(),max_h))
                obj.setProperty("screenAdapted",True)
        return False
