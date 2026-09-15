import pygame

pygame.init()

WIDTH, HEIGHT = 600, 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Drag the Red Dot")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

WHITE = (255, 255, 255)
RED = (200, 30, 30)
BLACK = (0, 0, 0)

dot_pos = [WIDTH // 2, HEIGHT // 2]
dot_radius = 20
dragging = False

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            dx = mx - dot_pos[0]
            dy = my - dot_pos[1]
            if dx * dx + dy * dy <= dot_radius * dot_radius:
                dragging = True

        elif event.type == pygame.MOUSEBUTTONUP:
            dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if dragging:
                dot_pos[0], dot_pos[1] = event.pos

    screen.fill(WHITE)

    pygame.draw.circle(screen, RED, dot_pos, dot_radius)

    coord_text = font.render(f"X: {dot_pos[0]}   Y: {dot_pos[1]}", True, BLACK)
    text_rect = coord_text.get_rect(center=(WIDTH // 2, HEIGHT - 30))
    screen.blit(coord_text, text_rect)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
