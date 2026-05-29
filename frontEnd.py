" Program that shows a user an optimized map of getting to rides at the amusement park Universal"
import pygame
import requests
import threading
import Data


pygame.init()

screen = pygame.display.set_mode((1200,800))
pygame.display.set_caption("front_end")

threading.Thread(target=Data.update_backend, daemon=True).start()

clock = pygame.time.Clock()

##map image and scaling
mapImage=pygame.image.load("map.png")
mapImage = pygame.transform.scale(mapImage, (1000, 800))

#images
hulk_img = pygame.image.load("hulk_logo.webp")
hulk_img = pygame.transform.scale(hulk_img, (60, 60))

#image array
ride_images = {
    "hulk": hulk_img,
}



# button positions
buttons = [
    [490, 620, False, "hulk"],
    [457, 622, False, "stormForce"],
    [404, 574, False, "doctorDoom"],
    [410, 530, False, "spiderMan"],
    [394, 380, False, "bilgeRat"],
    [276, 379, False, "ripsawFalls"],
    [271, 246, False, "skullIsland"],
    [514, 308, False, "velociCoaster"],
    [412, 217, False, "riverAdventure"],
    [745, 204, False, "hogwartsTrain"],
    [635, 186, False, "hippogriff"],
    [717, 248, False, "hagrid"],
    [715, 495, False, "drSuessAirRide"],
    [715, 495, False, "caroSuessel"],
    [714, 572, False, "oneFishtwoFish"],
    [695, 597, False, "catInTheHat"],
    [605, 192, False, "harryPotter"]
]

##wait times connection
ride_waits = {}
popup = None  # will store (x, y, text)


running = True

while running:

    # check events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        if event.type==pygame.MOUSEBUTTONDOWN:
            mx, my=pygame.mouse.get_pos()
            
            popup= None #resets popup at every click
            
            for button in buttons:
                x, y = button[0], button[1]

                distance_squared = (mx - x)**2 + (my - y)**2

                if distance_squared <= 400:

                    # turn ALL buttons off first
                    for b in buttons:
                        b[2] = False

                    # turn clicked one ON
                    button[2] = True

                    # popup
                    ride_id = button[3]
                    wait = Data.ride_waits.get(ride_id, None)

                    if wait is None:
                        text = f"{ride_id}\nLoading..."
                    else:
                        text = f"{ride_id} - {wait} min"

                        popup = (x + 15, y - 15, text)

                    

    # fill screen
    screen.fill((255,255,255))   

    #displaying the image
    screen.blit(mapImage, (0, 0))
    
    # draw buttons
 # draw buttons
    for button in buttons:
        x = button[0]
        y = button[1]
        clicked = button[2]
        ride_id = button[3]

        # ============================================================
        # CHANGE 3: Blit the image if one exists, otherwise draw circle
        # ============================================================
        if ride_id in ride_images:
            img = ride_images[ride_id]
            img_rect = img.get_rect(center=(x, y))
            if clicked:
                pygame.draw.circle(screen, (0, 255, 0), (x, y), 18)  # green highlight behind image
            screen.blit(img, img_rect)
        else:
            color = (0, 255, 0) if clicked else (255, 0, 0)
            pygame.draw.circle(screen, color, (x, y), 10)

            
    if popup is not None:

        px, py, text = popup

        pygame.draw.rect(screen, (30, 30, 30), (px, py, 120, 50))  # box
        pygame.draw.rect(screen, (255, 255, 255), (px, py, 120, 50), 2)  # border

        font = pygame.font.SysFont("Arial", 14)
        
        


        lines = text.split("\n")
        
        for i, line in enumerate(lines):
                label = font.render(line, True, (255, 255, 255))
                screen.blit(label, (px + 10, py + 10 + i * 18))
            
            
    # update window
    pygame.display.update()

    # FPS
    clock.tick(60)

pygame.quit()