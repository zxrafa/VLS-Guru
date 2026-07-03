from formations_coordinates import FORMATIONS

def main():
    card_w, card_h = 120, 168
    hw, hh = card_w / 2, card_h / 2
    
    any_overlaps = False
    for formation_name, coords in FORMATIONS.items():
        positions = list(coords.items())
        overlaps_in_formation = []
        for i in range(len(positions)):
            pos_a, data_a = positions[i]
            cx_a, cy_a = data_a["center"]
            # Box A
            ax1, ax2 = cx_a - hw, cx_a + hw
            ay1, ay2 = cy_a - hh, cy_a + hh
            
            for j in range(i + 1, len(positions)):
                pos_b, data_b = positions[j]
                cx_b, cy_b = data_b["center"]
                # Box B
                bx1, bx2 = cx_b - hw, cx_b + hw
                by1, by2 = cy_b - hh, cy_b + hh
                
                # Check overlap
                overlap_x = not (ax2 <= bx1 or bx2 <= ax1)
                overlap_y = not (ay2 <= by1 or by2 <= ay1)
                
                if overlap_x and overlap_y:
                    overlaps_in_formation.append((pos_a, pos_b))
                    any_overlaps = True
                    
        if overlaps_in_formation:
            print(f"Formation {formation_name} has overlaps: {overlaps_in_formation}")
        else:
            print(f"Formation {formation_name} is CLEAN!")
            
    if not any_overlaps:
        print("ALL FORMATIONS ARE 100% CLEAN WITH 120x168 CARD SIZE!")

if __name__ == "__main__":
    main()
