#include <stdio.h>

int getMenuChoice();

int main()
{
    int choice, studentCount = 0, qCount=0, pCount=0, hmCount=0, qPerfectTotal=0, pPerfectTotal=0, hmPerfectTotal=0, qPerfectCount=0, pPerfectCount=0, hmPerfectCount=0;
    float finalGrade=0.0, passingGrade, perfectFinalGrade;
    char studentNames[50][50];
    float studentGrades[50];
    do{
        choice=getMenuChoice();
        switch(choice){
            case 0:
                break;
            case 1:
                printf("\nEnter number of quizzes: ");
                scanf("%d",&qCount);
                for(int i=0; i<qCount; i++){
                    int qPerfect;
                    printf("\nEnter perfect score for quiz %d: ",i+1);
                    scanf("%d",&qPerfect);
                    qPerfectTotal+=qPerfect;
                    qPerfectCount++;
                }
                printf("\nEnter number of projects: ");
                scanf("%d",&pCount);
                for(int i=0; i<pCount; i++){
                    int pPerfect;
                    printf("\nEnter perfect score for project %d: ",i+1);
                    scanf("%d",&pPerfect);
                    pPerfectTotal+=pPerfect;
                    pPerfectCount++;
                }
                printf("\nEnter number of homework: ");
                scanf("%d",&hmCount);
                for(int i=0; i<hmCount; i++){
                    int hmPerfect;
                    printf("\nEnter perfect score for homework %d: ",i+1);
                    scanf("%d",&hmPerfect);
                    hmPerfectTotal+=hmPerfect;
                    hmPerfectCount++;
                }
                perfectFinalGrade=(qPerfectTotal/qPerfectCount*0.5)+(pPerfectTotal/pPerfectCount*0.3)+(hmPerfectTotal/hmPerfectCount*0.2);
                break;
            case 2:
                printf("\nEnter number of students: ");
                scanf("%d",&studentCount);
                for(int i=0; i<studentCount; i++){
                    printf("\nstudent %d of %d",i+1,studentCount);
                    printf("\nEnter name of student %d: ",i+1);
                    scanf("%s",studentNames[i]);
                }
                break;
            case 3:
                for(int i=0; i<studentCount; i++){
                    int qTotal=0, pTotal=0, hmTotal=0;
                    printf("\nStudent %d of %d",i+1,studentCount);
                    for(int j=0; j<qCount; j++){
                        int quiz;
                        printf("\nquizz %d of %d",j+1,qCount);
                        printf("\nEnter score for quiz %d: ",j+1);
                        scanf("%d",&quiz);
                        qTotal+=quiz;
                    }
                    for(int k=0; k<pCount; k++){
                        int project;
                        printf("\nproject %d of %d",k+1,pCount);
                        printf("\nEnter score for project %d: ",k+1);
                        scanf("%d",&project);
                        pTotal+=project;
                    }
                    for(int l=0; l<qCount; l++){
                        int homework;
                        printf("\nhomework %d of %d",l+1,hmCount);
                        printf("\nEnter score for homework %d: ",l+1);
                        scanf("%d",&homework);
                        hmTotal+=homework;
                    }
                    studentGrades[i]=(qTotal/qCount*0.5)+(pTotal/pCount*0.3)+(hmTotal/hmCount*0.2);
                }
                break;
            case 4:
                passingGrade=perfectFinalGrade*0.6;
                for(int i=0; i<studentCount; i++){
                    printf("\nName: %s",studentNames[i]);
                    printf("\nPassing grade: %.2f", passingGrade);
                    printf("\nYour grade: %.2f", studentGrades[i]);
                    if(studentGrades[i]>=passingGrade){
                        printf("\nPassed");
                    }
                    else{
                        printf("\nFailed");
                    }
                }
                break;
        }
    }while(choice!=0);

    return 0;
}

int getMenuChoice()
{
    int choice;
    printf("\n(1) Initialize perfect scores");
    printf("\n(2) Initialize students");
    printf("\n(3) Initialize student scores");
    printf("\n(4) Display students grades");
    printf("\n(0) Exit");
    printf("\nEnter choice: ");
    scanf("%d",&choice);
    return choice;
}

