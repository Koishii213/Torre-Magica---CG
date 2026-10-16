import glfw
from OpenGL.GL import *
from OpenGL.GLU import *
import math

#configuração de câmera

Camera_pos = [0.0, 1.7,5.0]

camera_horizontal = -90
camera_vertical = 0.0

velocidade = 5.0
sensibilidade = 0.1

ultimoX = None 
ultimoY = None

#movimento da visão

def mouse(window, xpos, ypos):
    global ultimoX, ultimoY
    global camera_vertical, camera_horizontal
    
    if ultimoX == None:
        ultimoX = xpos
        ultimoY = ypos
        return
    
    #calculo de deslocamento visão
    
    dx = xpos - ultimoX
    dy = ultimoY - ypos
    
    ultimoX = xpos
    ultimoY = ypos
    
    camera_horizontal += dx*sensibilidade
    camera_vertical += dy*sensibilidade
    
    camera_vertical = max(-89, min(89, camera_vertical))
    
# movimento

def movimento(window, delta_time):
    global Camera_pos
    
    angulo = math.radians(camera_horizontal)
    
    frenteX = math.cos(angulo)
    FrenteZ = math.sin(angulo)
    
    velocidade_Movimento = velocidade * delta_time
    
    if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
        Camera_pos[0] += frenteX * velocidade_Movimento
        Camera_pos[2] += FrenteZ * velocidade_Movimento
    
    if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
        Camera_pos[0] -= frenteX * velocidade_Movimento
        Camera_pos[2] -= FrenteZ * velocidade_Movimento
    
#funções de desenho

def desenhar_piso():
    glColor3f(0.2,0.2,0.10)
    
    glBegin(GL_TRIANGLES)
    
    glVertex3f(-10, 0, -10)
    glVertex3f( 10, 0, -10)
    glVertex3f( 10, 0,  10)

    # Segundo triângulo
    glVertex3f(-10, 0, -10)
    glVertex3f( 10, 0,  10)
    glVertex3f(-10, 0,  10)
    
    glVertex3f(-10, 5, -10)
    glVertex3f( 10, 5, -10)
    glVertex3f( 10, 5,  10)
    
        # Segundo triângulo
    glVertex3f(-10, 5, -10)
    glVertex3f( 10, 5,  10)
    glVertex3f(-10, 5,  10)

    glEnd()

def render():
    #tratamento da câmera
    
    horizontal = math.radians(camera_horizontal)
    vertical = math.radians(camera_vertical)
    
    frontX = math.cos(horizontal)*math.cos(vertical)
    frontY = math.sin(vertical)
    frontZ = math.sin(horizontal)*math.cos(vertical)
    
    glClearColor(0.15, 0.15, 0.20, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    gluLookAt(
        Camera_pos[0],
        Camera_pos[1],
        Camera_pos[2],
        
        Camera_pos[0]+frontX,
        Camera_pos[1]+frontY,
        Camera_pos[2]+frontZ,
        
        0,1,0
    )

    desenhar_piso()
    

def main():
    if not glfw.init():
        return
    
    ultimo_tempo = glfw.get_time()

    window = glfw.create_window(
        1920, 1080, "Torre Magica", None, None
    )

    if not window:
        glfw.terminate()
        return

    glfw.make_context_current(window)

    glEnable(GL_DEPTH_TEST)

    # Configuração da projeção
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, 1920/1080, 0.1, 100)
    
    glfw.set_input_mode(
        window,
        glfw.CURSOR,
        glfw.CURSOR_DISABLED
    )

    glfw.set_cursor_pos_callback(window, mouse)
    
    while not glfw.window_should_close(window):
        glfw.poll_events()

        tempo_atual = glfw.get_time()
        delta_time = tempo_atual - ultimo_tempo
        ultimo_tempo = tempo_atual
        movimento(window, delta_time)
        
        render()

        glfw.swap_buffers(window)

    glfw.terminate()

if __name__ == '__main__':
    main()