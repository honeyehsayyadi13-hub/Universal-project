" Program that shows a user an optimized map of getting to rides at the amusement park Universal"
import pygame

pygame.init()

screen = pygame.display.set_mode((1200,800))
pygame.display.set_caption("front_end")

clock = pygame.time.Clock()

mapImage=pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (1000, 900))


running = True

while running:

    # check events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # fill screen
    screen.fill((255,255,255))   

    #displaying the image
    screen.blit(mapImage, (0, 0))
    
    # update window
    pygame.display.update()

    # FPS
    clock.tick(60)

pygame.quit()