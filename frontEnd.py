" Program that shows a user an optimized map of getting to rides at the amusement park Universal"
import pygame
from tkinter import *

pygame.init()
win = Tk()

clock = pygame.time.Clock()


screen = pygame.display.set_mode((1200,800))
pygame.display.set_caption("front_end")

clock = pygame.time.Clock()

##map image
mapImage=pygame.image.load("map.png")
##scaling image
mapImage = pygame.transform.scale(mapImage, (1000, 800))

##clickable buttons work

# button positions
buttons = [
    (300, 200, False),
    (500, 350, False),
    (700, 150, False)
]

running = True

while running:

    # check events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        if event.type==pygame.MOUSEBUTTONDOWN:
            mx, my=pygame.mouse.get_pos()
            for button in buttons:
                x=button[0]
                y=button[1]
                distance=((mx-x)**2+(my-y)**2)*0.5
                
                if distance <=10:
                    button[2]=True

                    

    # fill screen
    screen.fill((255,255,255))   

    #displaying the image
    screen.blit(mapImage, (0, 0))
    
    # draw buttons
    for button in buttons:

        x = button[0]
        y = button[1]
        clicked = button[2]

        # if clicked -> green
        if clicked:
            color = (0,255,0)
        else:
            color = (255,0,0)

        pygame.draw.circle(screen, color, (x,y), 10)
    
    # update window
    pygame.display.update()

    # FPS
    clock.tick(60)

pygame.quit()