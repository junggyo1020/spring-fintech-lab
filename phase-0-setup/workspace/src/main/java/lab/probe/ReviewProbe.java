package lab.probe;

// 리뷰 봇 연동 테스트용 파일. 테스트 PR을 닫으면 함께 삭제된다.
public class ReviewProbe {
    private double balance;

    public void withdraw(double amount) {
        if (balance >= amount) {
            balance = balance - amount;
        }
    }

    public double interest(double rate) {
        return balance * rate / 365;
    }
}
