void TC1_fopen_win32_fclose_true(void) {
#ifdef _WIN32
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif
    fclose((FILE*)0);
}

void TC2_fopen_fclose_same_pc(void) {
#ifdef _WIN32
    FILE *f = fopen("a.txt", "r");
    if (f) fclose(f);
#endif
}

void TC3_two_platform_fopen_no_fclose(void) {
#ifdef _WIN32
    FILE *f1 = fopen("a.txt", "r");
    (void)f1;
#endif
#ifdef _WIN64
    FILE *f2 = fopen("b.txt", "r");
    (void)f2;
#endif
    fclose((FILE*)0);
}

void TC4_fopen_ifdefA_fclose_ifdefB(void) {
#ifdef FEATURE_A
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif
#ifdef FEATURE_B
    fclose((FILE*)0);
#endif
}

void TC5_fopen_ifdef_fclose_outside(void) {
#ifdef FEATURE_A
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif
    fclose((FILE*)0);
}

void TC6_fopen_ifndef_fclose_ifdef(void) {
#ifndef FEATURE_A
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif
#ifdef FEATURE_A
    fclose((FILE*)0);
#endif
}

void TC7_fopen_elif_fclose_only_A(void) {
#if defined(FEATURE_A)
    FILE *f = fopen("a.txt", "r");
    (void)f;
#elif defined(FEATURE_B)
    FILE *f = fopen("b.txt", "r");
    (void)f;
#endif

#ifdef FEATURE_A
    fclose((FILE*)0);
#endif
}

void TC8_nested_fopen_AB_fclose_A(void) {
#ifdef FEATURE_A
  #ifdef FEATURE_B
    FILE *f = fopen("a.txt", "r");
    (void)f;
  #endif
  fclose((FILE*)0);
#endif
}

void TC9_nested_fopen_AB_fclose_AB(void) {
#ifdef FEATURE_A
  #ifdef FEATURE_B
    FILE *f = fopen("a.txt", "r");
    if (f) fclose(f);
  #endif
#endif
}

void TC10_multi_fopen_A_B_fclose_A(void) {
#ifdef FEATURE_A
    FILE *fa = fopen("a.txt", "r");
    (void)fa;
#endif
#ifdef FEATURE_B
    FILE *fb = fopen("b.txt", "r");
    (void)fb;
#endif
#ifdef FEATURE_A
    fclose((FILE*)0);
#endif
}

void TC11_if_expr_mismatch(void) {
#if defined(FEATURE_A) && !defined(FEATURE_B)
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif

#if defined(FEATURE_A) && defined(FEATURE_B)
    fclose((FILE*)0);
#endif
}

void TC12_if_expr_partial_overlap(void) {
#if defined(FEATURE_A) && (defined(FEATURE_B) || defined(FEATURE_C))
    FILE *f = fopen("a.txt", "r");
    (void)f;
#endif

#if defined(FEATURE_A) && defined(FEATURE_B)
    fclose((FILE*)0);
#endif
}

void TC13_deep_nested_fopen_many_regions(void) {
#ifdef F1
  #ifdef F2
    #ifdef F3
      #ifdef F4
        #ifdef F5
          #ifdef F6
            #ifdef F7
              #ifdef F8
                #ifdef F9
                  #ifdef F10
                    FILE *f = fopen("deep.txt", "r");
                    (void)f;
                  #endif
                #endif
              #endif
            #endif
          #endif
        #endif
      #endif
    #endif
  #endif
#endif

#ifdef F1
  #ifdef F2
    #ifdef F3
      /* fopen in a different (shallower) condition */
      FILE *f2 = fopen("shallow.txt", "r");
      (void)f2;
    #endif
  #endif
#endif

#ifdef F1
  #ifdef F2
    #ifdef F3
        fclose((FILE*)0); /* close only for some configurations */
    #endif
  #endif
#endif
}

void TC14_malloc_A_free_B(void) {
#ifdef FEATURE_A
    void *p = malloc(64);
    (void)p;
#endif
#ifdef FEATURE_B
    free((void*)0);
#endif
}

void TC15_malloc_free_same_A(void) {
#ifdef FEATURE_A
    void *p = malloc(64);
    free(p);
#endif
}

void TC16_nested_malloc_AB_free_A(void) {
#ifdef FEATURE_A
  #ifdef FEATURE_B
    void *p = malloc(128);
    (void)p;
  #endif
  free((void*)0);
#endif
}

void TC17_multi_malloc_A_B_free_B(void) {
#ifdef FEATURE_A
    void *pa = malloc(16);
    (void)pa;
#endif
#ifdef FEATURE_B
    void *pb = malloc(32);
    free(pb);
#endif
}

void TC18_malloc_elif_free_only_A(void) {
#if defined(FEATURE_A)
    void *p = malloc(10);
    (void)p;
#elif defined(FEATURE_B)
    void *p = malloc(20);
    (void)p;
#endif

#ifdef FEATURE_A
    free((void*)0);
#endif
}

void TC19_malloc_if_expr_mismatch(void) {
#if defined(FEATURE_A) && !defined(FEATURE_B)
    void *p = malloc(100);
    (void)p;
#endif

#if defined(FEATURE_A) && defined(FEATURE_B)
    free((void*)0);
#endif
}

void TC20_malloc_elif_free_only_A(void) {
#if defined(FEATURE_A)
    void *p = malloc(10);
    (void)p;
#elif defined(FEATURE_B)
    void *p = malloc(20);
    (void)p;
#elif defined(FEATURE_C)
    void *p = malloc(20);
    (void)p;
#endif

#ifdef FEATURE_A
    free((void*)0);
#endif
}













